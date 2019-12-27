from flask_restplus import Api

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

    return result_to_dicts(type(models[0]).query.all())
