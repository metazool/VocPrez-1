from flask import Blueprint, Response, request, render_template, Markup, g
from model.vocabulary import VocabularyRenderer
from model.concept import ConceptRenderer
from model.collection import CollectionRenderer
from model.skos_register import SkosRegisterRenderer
import _config as config
import markdown
from data.source._source import Source
from data.source.VOCBENCH import VbException
import json

routes = Blueprint('routes', __name__)


def render_invalid_vocab_id_response():
    msg = """The vocabulary ID that was supplied was not known. It must be one of these: \n\n* """ + '\n* '.join(g.VOCABS.keys())
    msg = Markup(markdown.markdown(msg))
    return render_template('error.html', title='Error - invalid vocab id', heading='Invalid Vocab ID', msg=msg)
    # return Response(
    #     'The vocabulary ID you\'ve supplied is not known. Must be one of:\n ' +
    #     '\n'.join(g.VOCABS.keys()),
    #     status=400,
    #     mimetype='text/plain'
    # )


def render_vb_exception_response(e):
    e = json.loads(str(e))
    msg = e['stresponse']['msg']
    if 'not an open project' in msg:
        invalid_vocab_id = msg.split('not an open project:')[-1]
        msg = 'The VocBench instance returned with an error: **{}** is not an open project.'.format(invalid_vocab_id)
        msg = Markup(markdown.markdown(msg))
    return render_template('error.html', title='Error', heading='VocBench Error', msg=msg)


def render_invalid_object_class_response(vocab_id, uri, c_type):
    msg = """No valid *Object Class URI* found for vocab_id **{}** and uri **{}** 
    
Instead, found **{}**.""".format(vocab_id, uri, c_type)
    msg = Markup(markdown.markdown(msg))
    return render_template('error.html', title='Error - Object Class URI', heading='Concept Class Type Error', msg=msg)


def get_a_vocab_key():
    """
    Get the first key from the g.VOCABS dictionary.

    :return: Key name
    :rtype: str
    """
    return next(iter(g.VOCABS))


@routes.route('/')
def index():
    return render_template(
        'index.html',
        title=config.TITLE,
        navs={},
        config=config,
        voc_key=get_a_vocab_source_key()
    )


def get_a_vocab_source_key():
    """
    Get the first key from the config.VOCABS dictionary.

    :return: Key name
    :rtype: str
    """
    return next(iter(g.VOCABS))


def match(vocabs, query):
    """
    Generate a generator of vocabulary items that match the search query

    :param vocabs: The vocabulary list of items.
    :param query: The search query string.
    :return: A generator of words that match the search query.
    :rtype: generator
    """
    for word in vocabs:
        if query.lower() in word['title'].lower():
            yield word


@routes.route('/vocabulary/')
def vocabularies():
    page = int(request.values.get('page')) if request.values.get('page') is not None else 1
    per_page = int(request.values.get('per_page')) if request.values.get('per_page') is not None else 20

    # TODO: replace this logic with the following
    #   1. read all static vocabs from g.VOCABS
    # get this instance's list of vocabs
    vocabs = []  # local copy (to this request) for sorting
    for k, v in g.VOCABS.items():
        v['vocab_id'] = k
        v['uri'] = request.base_url + k
        vocabs.append(v)
    vocabs.sort(key=lambda item: item['title'])
    total = len(g.VOCABS.items())

    # Search
    query = request.values.get('search')
    results = []
    if query:
        for m in match(vocabs, query):
            results.append(m)
        vocabs[:] = results
        vocabs.sort(key=lambda item: item['title'])
        total = len(vocabs)

    # generate vocabs list for requested page and per_page
    start = (page-1)*per_page
    end = start + per_page
    vocabs = vocabs[start:end]

    # render the list of vocabs
    return SkosRegisterRenderer(
        request,
        [],
        vocabs,
        'Vocabularies',
        total,
        search_query=query,
        search_enabled=True,
        vocabulary_url=['http://www.w3.org/2004/02/skos/core#ConceptScheme']
    ).render()


@routes.route('/vocabulary/<vocab_id>')
def vocabulary(vocab_id):
    if vocab_id not in g.VOCABS.keys():
        return render_invalid_vocab_id_response()

    # get vocab details using appropriate source handler
    try:
        v = Source(vocab_id, request).get_vocabulary()
    except VbException as e:
        return render_vb_exception_response(e)

    return VocabularyRenderer(
        request,
        v
    ).render()


@routes.route('/vocabulary/<vocab_id>/concept/')
def vocabulary_list(vocab_id):
    if vocab_id not in g.VOCABS.keys():
        return render_invalid_vocab_id_response()

    v = Source(vocab_id, request)
    concepts = v.list_concepts()
    concepts.sort(key=lambda x: x['title'])
    total = len(concepts)

    # Search
    query = request.values.get('search')
    results = []
    if query:
        for m in match(concepts, query):
            results.append(m)
        concepts[:] = results
        concepts.sort(key=lambda x: x['title'])
        total = len(concepts)

    page = int(request.values.get('page')) if request.values.get('page') is not None else 1
    per_page = int(request.values.get('per_page')) if request.values.get('per_page') is not None else 20
    start = (page - 1) * per_page
    end = start + per_page
    concepts = concepts[start:end]

    test = SkosRegisterRenderer(
        request,
        [],
        concepts,
        g.VOCABS[vocab_id]['title'] + ' concepts',
        total,
        search_query=query,
        search_enabled=True,
        vocabulary_url=[request.url_root + 'vocabulary/' + vocab_id],
        vocab_id=vocab_id
    )
    return test.render()


@routes.route('/collection/')
def collections():
    return render_template(
        'register.html',
        title='Collections',
        register_class='Collections',
        navs={}
    )


@routes.route('/object')
def object():
    """
    This is the general RESTful endpoint and corresponding Python function to handle requests for individual objects,
    be they a Vocabulary, Concept Scheme, Collection or Concept. Only those 4 classes of object are supported for the
    moment.

    An HTTP URI query string argument parameter 'vocab_id' must be supplied, indicating the vocab this object is within
    An HTTP URI query string argument parameter 'uri' must be supplied, indicating the URI of the object being requested

    :return: A Flask Response object
    :rtype: :class:`flask.Response`
    """
    vocab_id = request.values.get('vocab_id')
    uri = request.values.get('uri')

    # check this vocab ID is known
    if vocab_id not in g.VOCABS.keys():
        return Response(
            'The vocabulary ID you\'ve supplied is not known. Must be one of:\n ' +
            '\n'.join(g.VOCABS.keys()),
            status=400,
            mimetype='text/plain'
        )

    if uri is None:
        return Response(
            'A Query String Argument \'uri\' must be supplied for this endpoint, '
            'indicating an object within a vocabulary',
            status=400,
            mimetype='text/plain'
        )

    try:
        # TODO reuse object within if, rather than re-loading graph
        c = Source(vocab_id, request).get_object_class()

        if c == 'http://www.w3.org/2004/02/skos/core#Concept':
            concept = Source(vocab_id, request).get_concept()
            return ConceptRenderer(
                request,
                concept
            ).render()
        elif c == 'http://www.w3.org/2004/02/skos/core#Collection':
            collection = Source(vocab_id, request).get_collection(uri)

            return CollectionRenderer(
                request,
                collection
            ).render()
        else:
            return render_invalid_object_class_response(vocab_id, uri, c)
    except VbException as e:
        return render_vb_exception_response(e)


@routes.route('/about')
def about():
    import os

    # using basic Markdown method from http://flask.pocoo.org/snippets/19/
    with open(os.path.join(config.APP_DIR, 'README.md')) as f:
        content = f.read()

    # make images come from wed dir
    content = content.replace('view/static/system.svg',
                              request.url_root + 'static/system.svg')
    content = Markup(markdown.markdown(content))

    return render_template(
        'about.html',
        title='About',
        navs={},
        content=content
    )


@routes.route('/test')
def test():
    txt = ''
    # for vocab_id, details in g.VOCABS.items():
    #     txt = txt + '{}: {}\n'.format(vocab_id, details['title'])

    import os
    import pickle
    import pprint
    vocabs_file_path = os.path.join(config.APP_DIR, 'VOCABS.p')
    if os.path.isfile(vocabs_file_path):
        with open(vocabs_file_path, 'rb') as f:
            txt = str(pickle.load(f))
            f.close()

    return Response(txt, mimetype='text/plain')
