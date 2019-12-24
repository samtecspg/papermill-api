import json
import os
import re
import time

from botocore.exceptions import ClientError, ParamValidationError
from flask import request, Response
from flask_restplus import Resource
from flask_restplus import fields

import app.services.run_services as rs
from app.main.views import api
from .errors import InvalidUsage

run_ns = api.namespace('run', description='For running notebooks')
render_template_model = run_ns.model('render_template', {
    "name": fields.String,
    "args": fields.Raw
}
                                     )

run_post_model = run_ns.model('run_post', {
    "parameters": fields.Raw,
    "template": fields.Nested(render_template_model)
}
                              )


# this decorator will do some preprocessing common to all run requests to populate values used by 'run_notebook'
# and the templating functionality
def get_path(f):
    def wrapper(self):

        # What type of service the notebook is located on.
        # so far, {'s3','local'}
        data = dict(request.args)

        location = data.get("location", None)
        notebook = data.get("notebook", None)

        # in order to generalize this in both cases
        # post body
        if self.api.payload:

            user_out = self.api.payload.get("outputNotebookPath", None)

        # query args
        else:
            user_out = data.get("outputNotebookPath", None)

        notebook = notebook.replace("s3://", "")

        path_array = notebook.split('/')

        filename = path_array[-1]
        del path_array[-1]

        # TODO is this necessary given the file name builder below?
        # insert file extension if not present
        if not re.search('\.ipynb$', filename):
            filename += ".ipynb"

        time_str = time.strftime("%Y%m%d%H%M%S")
        out_notebook_name = filename.replace(".ipynb", "") + "_out_" + time_str + ".ipynb"

        if location.lower() == "s3":

            try:
                if len(path_array) < 1:
                    # prevents unhandled exception of constructing path to notebook: os.path.join(*path_array)
                    raise InvalidUsage("Invalid notebook location")

            except InvalidUsage as error:
                response = Response(json.dumps(error.to_dict()))
                response.status_code = error.status_code
                return response

            bucket = path_array[0]
            home = path_array[1]
            user = path_array[2]
            out_path = "s3://" + bucket + "/" + os.path.join(*path_array[1:]) + "/"
            in_notebook = out_path + filename
            user_notebook_path = os.path.join(*path_array[3:])

            paths_dict = {
                "location": location,
                "bucket": bucket,
                "home": home,
                "user": user,
                "user_notebook_path": user_notebook_path,
                "in_notebook": in_notebook,
                "out_path": out_path,
                "out_notebook_name": out_notebook_name,
                "user_out": user_out
            }

        else:

            out_path = "/".join(path_array) + "/"
            in_notebook = out_path + filename

            paths_dict = {
                "location": location,
                "in_notebook": in_notebook,
                "out_path": out_path,
                "out_notebook_name": out_notebook_name,
                "user_out": user_out
            }

        return f(self, paths_dict)

    return wrapper


@run_ns.route('/', methods=['GET', 'POST'])
class RunNotebook(Resource):

    @api.doc(params={'template': 'name of a template to used to store the resulting notebook',
                     'outputNotebookPath': 'path to store the output notebook'
                     }
             )
    @api.param('notebook', 'path to the resource on S3', required=True)
    @api.param('location', 'specify whether the notebook resides in s3 or local', required=True, enum=["s3", "local"])
    @api.param('template', 'name of a template to used to store the resulting notebook')
    @get_path
    def get(self, paths_dict):

        data = dict(request.args)

        try:
            if "template" in data and "outputNotebookPath" in data:
                raise InvalidUsage("either 'outputNotebookPath' or 'template' is supported not both")
        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        try:
            return rs.get(data=data, paths_dict=paths_dict)
        except ClientError as error:
            response = Response(json.dumps(error.response["Error"]))
            response.status_code = int(error.response["Error"]["Code"])
            return response
        except ParamValidationError as error:
            error.kwargs.update({"message": "Check 'location' parameter."})
            response = Response(json.dumps(error.kwargs))
            response.status_code = 400
            return response

    @api.param('notebook', 'path to the resource on S3', required=True)
    @api.param('location', 'specify whether the notebook resides in s3 or local', required=True, enum=["s3", "local"])
    @api.expect(run_post_model)
    @get_path
    def post(self, paths_dict):

        # TODO currently fails to give appropriate message if the json is invalid.
        if request.get_json(force=True):

            data = request.get_json()

            try:
                return rs.post(paths_dict=paths_dict, data=data)
            except InvalidUsage as error:
                response = Response(json.dumps(error.to_dict()))
                response.status_code = error.status_code
                return response
            except ClientError as error:
                response = Response(json.dumps(error.response["Error"]))
                response.status_code = int(error.response["Error"]["Code"])
                return response
            except ParamValidationError as error:
                error.kwargs.update({"message": "Check 'local' parameter."})
                response = Response(json.dumps(error.kwargs))
                response.status_code = 400
                return response
        else:
            raise InvalidUsage("only application/json supported")
