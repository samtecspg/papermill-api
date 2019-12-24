from flask_restplus import Api, fields

from . import main
from .. import db as sadb

api = Api(main, title="Papermill API", version="1.0")


# creates a list containing the dictionary representation of
# model objects as defined in the as_dict method of each model
def result_to_dicts(result_rows):
    result = []
    for each in result_rows:
        result.append(each.as_dict())
    return result


# saves a list of models of the same type and returns a
# list with all models now in the database
def save_models(models):
    if len(models) < 1:
        return []

    for each in models:
        sadb.session.add(each)
    sadb.session.commit()

    response = result_to_dicts(type(models[0]).query.all())

    return response


templates_ns = api.namespace('template', description='For defining, retrieving and deleting templates')
# gets and sets the template which is default.

templates_post_model = templates_ns.model('template_post', {
    "name": fields.String,
    "content": fields.String,
    "default": fields.String(enum=["true", "false", "t", "f", "yes", "no", "y", "n",
                                   "on", "off", "0", "1"],
                             description="a string representing a truth value")
}
                                          )

templates_delete_model = templates_ns.model('template_delete', {
    "name": fields.String
}
                                            )

template_ns = api.namespace('template', description='For defining and retrieving templates')

# gets and sets the template which is default.


# gets and sets templates with url parameters
