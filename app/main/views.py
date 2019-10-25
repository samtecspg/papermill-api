from flask import request, Response, render_template_string, jsonify, abort
from flask_restplus import Resource, Api, fields
from sqlalchemy.orm.exc import NoResultFound
import papermill as pm
import scrapbook as sb
import re
import json
import os
import time
from distutils.util import strtobool
from . import main
from .. import db as sadb
from app.models import DefaultTemplate, Template
from .errors import InvalidUsage
from botocore.exceptions import ClientError, ParamValidationError

api = Api(main, title="Papermill API", version="1.0")

# gets the record in the DefaultTemplate table that points to the current default template
def get_default_template_record():
    return DefaultTemplate.query.first()

def get_default_template():
    default = get_default_template_record()
    if not default is None:
        return default.template
    return None

# creates a list containing the dictionary representation of
# model objects as defined in the as_dict method of each model
def result_to_dicts(result_rows):
    result = []
    for each in result_rows:
        result.append(each.as_dict())
    return result

# saves a list of models of the same type and returns a
# list with all models now in the databse
def save_models(models):

    if len(models) < 1:
        return []

    for each in models:
        sadb.session.add(each)
    sadb.session.commit()

    response = result_to_dicts(type(models[0]).query.all())

    return response

run = api.namespace('run', description='For running notebooks')

render_template_model = run.model('render_template', {
    "name": fields.String,
    "args": fields.Raw
  }
)

run_post_model = run.model('run_post', {
                                     "parameters": fields.Raw,
                                     "template": fields.Nested(render_template_model)
                                }
)

# this decorator will do some preprecessing common to all run requests to populate values used by 'run_notebook'
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
            out_path = "s3://" + bucket +"/"+ os.path.join(*path_array[1:]) + "/"
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

            out_path = "/".join(path_array)+"/"
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


@run.route('/', methods=['GET', 'POST'])
class RunNotebook(Resource):

    @api.doc(params={'template': 'name of a template to used to store the resulting notebook',
                     'outputNotebookPath': 'path to store the output notebook'
                     }
             )
    @api.param('notebook', 'path to the resource on S3', required=True)
    @api.param('location', 'specify whether the notebook resides in s3 or local', required=True, enum=["s3", "local"])
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

        default = get_default_template()
        template = data.get("template",  None)
        template_args = {}
        template_args.update({"notebook_name": paths_dict["out_notebook_name"]})
        out_path = render(template, default, paths_dict["user_out"], paths_dict["out_path"], template_args=template_args)

        # TODO this leaves an empty directory if 'execute_notebook' is unsuccessful
        if "s3://" not in out_path:
            try:
                os.makedirs(out_path, mode=0o777, exist_ok=False)
            except:
                # directory exists
                pass

        outfile = os.path.join(out_path, paths_dict["out_notebook_name"])

        try:

            result = pm.execute_notebook(
                paths_dict["in_notebook"],
                outfile,
                parameters=data
            )

        except ClientError as error:
            response = Response(json.dumps(error.response["Error"]))
            response.status_code = int(error.response["Error"]["Code"])
            return response
        except ParamValidationError as error:
            error.kwargs.update({"message": "Check 'location' parameter."})
            response = Response(json.dumps(error.kwargs))
            response.status_code = 400
            return response

        nb = sb.read_notebook(outfile)
        json_result = {"result": nb.scraps.data_dict}

        if strtobool(request.args.get('returnNotebook') or "false"):
            json_result["notebook"] = result

        response = Response(json.dumps(json_result, indent=4), content_type="application/json")

        # insert 'statusCode' if defined in scrap data
        if nb.scraps.data_dict.get("statusCode", None):
            status = nb.scraps.data_dict.get("statusCode", None)
            response.status_code = status

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
                if "template" in data and "outputNotebookPath" in data:
                    raise InvalidUsage("either 'outputNotebookPath' or 'template' is supported not both")
            except InvalidUsage as error:
                response = Response(json.dumps(error.to_dict()))
                response.status_code = error.status_code
                return response

            # parameters sent to notebook
            parameters = data.get("parameters", None)

            default = get_default_template()
            template = data.get("template", None)
            template_args = {}
            template_args.update({"notebook_name": paths_dict["out_notebook_name"]})
            out_path = render(template, default, paths_dict["user_out"], paths_dict["out_path"], template_args=template_args)

        else:
            raise InvalidUsage("only application/json supported")

        if "s3://" not in out_path:
            try:
                os.makedirs(out_path, mode=0o777, exist_ok=False)
            except:
                # directory exists
                pass

        outfile = os.path.join(out_path, paths_dict["out_notebook_name"])

        try:

            result = pm.execute_notebook(
                paths_dict["in_notebook"],
                outfile,
                parameters=parameters
            )

        except ClientError as error:
            response = Response(json.dumps(error.response["Error"]))
            response.status_code = int(error.response["Error"]["Code"])
            return response
        except ParamValidationError as error:
            error.kwargs.update({"message": "Check 'local' parameter."})
            response = Response(json.dumps(error.kwargs))
            response.status_code = 400
            return response

        nb = sb.read_notebook(outfile)
        json_result = {"result": nb.scraps.data_dict}

        if strtobool(request.args.get('returnNotebook') or "false"):
            json_result["notebook"] = result

        response = Response(json.dumps(json_result, indent=4), content_type="application/json")

        # insert 'statusCode' if defined in scrap data
        if nb.scraps.data_dict.get("statusCode", None):
            status = nb.scraps.data_dict.get("statusCode", None)
            response.status_code = status

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


@templates_ns.route('/', methods=['GET', 'POST', 'PATCH', 'DELETE'])
class TemplatesRoutes(Resource):
    @api.param('default', 'Return only default template. Otherwise return all templates.',
               enum=["true", "false", "t", "f", "yes", "no", "y", "n", "on", "off", "0", "1"])
    def get(self):

        if strtobool(request.args.get('default') or "false"):
            return jsonify(get_default_template().as_dict() if get_default_template() else [])
        else:
            return list_templates()

    @templates_ns.expect(templates_delete_model)
    def delete(self):
        data = json.loads(request.data.decode())
        template = Template.query.filter_by(name=data["name"]).first()
        sadb.session.delete(template)
        sadb.session.commit()

        return list_templates()

    @templates_ns.expect(templates_post_model)
    def post(self):

        data = json.loads(request.data.decode())

        existing = Template.query.filter_by(name=data["name"])

        try:
            if existing.first():
                raise InvalidUsage("Template exists")

        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        t = Template(name=data["name"], content=data["content"])
        save_models([t])

        try:
            is_default = strtobool(data.get('default') or "false")
        except ValueError as error:
            message = dict({"Error": str(error)})
            response = Response(json.dumps(message, indent=4), content_type="application/json")
            response.status_code = 500
            return response
        if is_default:
            try:
                dt = DefaultTemplate.query.one()
            except:
                dt = DefaultTemplate()

            dt.template_id = t.id
            save_models([dt])

        return list_templates()

    @templates_ns.expect(templates_post_model)
    def patch(self):

        data = json.loads(request.data.decode())

        existing = Template.query.filter_by(name=data["name"]).first()

        try:
            if not existing:
                raise InvalidUsage("Template does not exist")

        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        if "content" in data:
            existing.content = data["content"]
        save_models([existing])

        set_default_template = strtobool(data.get('default') or "false")
        dt = DefaultTemplate.query.one()

        if set_default_template:
            dt.template_id = existing.id

        # unassign default if is false and this template is currently the default.
        elif dt.template_id == existing.id:
            dt.template_id = None

        save_models([dt])

        return list_templates()


template_ns = api.namespace('template', description='For defining and retrieving templates')
# gets and sets the template which is default.


# gets and sets templates with url parameters
@template_ns.route('/<path:template>', methods=['GET', 'DELETE'])
class TemplateRoutes(Resource):
    def get(self, template):

        response = result_to_dicts(Template.query.filter_by(name=template))

        return jsonify(response)

    def delete(self, template):

        existing = Template.query.filter_by(name=template).first()

        try:
            if not existing:
                raise InvalidUsage("Template does not exist")

        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        sadb.session.delete(existing)
        sadb.session.commit()

        return list_templates()

    @templates_ns.expect(templates_post_model)
    def post(self, template):

        data = json.loads(request.data.decode())

        existing = Template.query.filter_by(name=template)

        try:
            if existing.first():
                raise InvalidUsage("Template exists")

        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        t = Template(name=template, content=data["content"])
        save_models([t])
        if strtobool(data.get('default') or "false"):
            dt = DefaultTemplate.query.one()
            dt.template_id = t.id
            save_models([dt])

        return list_templates()


def list_templates():
    temp =Template.query.all()
    return jsonify(result_to_dicts(temp))


def default_template_parameters(f):
    def wrapper(template_name, default, user_out, outputpath, template_args):
        # some initial default args for things like a time stamp.
        template_args["timestamp"] = time.strftime("%Y%m%d%H%M%S")
        template_args["year"] = time.strftime("%Y")
        template_args["month"] = time.strftime("%m")
        template_args["day"] = time.strftime("%d")
        return f(template_name, default, user_out, outputpath, template_args=template_args)

    return wrapper


@default_template_parameters
# if the user specifies a template, render the template
# if the user specifies an output path, render that
# if neither of these are defined, render the default template
# If the default template does not exist, use the location of the input notebook
def render(template_name, default, user_out, outputpath, template_args={}):

    if template_name:

        try:
            t = Template.query.filter_by(name=template_name).one()
        except NoResultFound as error:
            response = Response(json.dumps({"error": "No template: " + template_name}))
            response.status_code = 404
            abort(response)

        rendered_template = render_template_string(t.content, args=template_args)

    elif user_out:
        rendered_template = render_template_string(user_out, args=template_args)
    elif default:
        rendered_template = render_template_string(default.content, args=template_args)
    else:
        rendered_template = render_template_string(outputpath, args=template_args)

    return rendered_template
