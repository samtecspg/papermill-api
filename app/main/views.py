from flask import request, Response, render_template_string, jsonify
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
from botocore.exceptions import ClientError


api = Api(main, title="Papermill API", version="1.0")

# gets the record in the DefaultTemplate table that points to the current default template
def get_default_template():
    return DefaultTemplate.query.first()

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

def get_path(f):
    def wrapper(self, notebook):
        path_array = notebook.split('/')

        try:
            if len(path_array) < 2:
                # prevents unhandled exception of constructing path to notebook: os.path.join(*path_array)
                raise InvalidUsage("Invalid notebook location")
        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response


        # get file name
        filename = path_array[-1]
        del path_array[-1]
        # insert file extension if not present
        if not re.search('\.ipynb$', filename):
            filename += ".ipynb"
        # path to notebook
        notebook = os.path.join(*path_array) + "/" + filename

        # build default output path and file name
        out_path = "s3://" + os.path.join(*path_array) + "/"
        time_str = time.strftime("%Y%m%d%H%M%S")

        out_name = filename.replace(".ipynb", "") + "_out_" + time_str + ".ipynb"
        return f(self, out_path, out_name, notebook)

    return wrapper

@run.route('/<path:notebook>', methods=['GET', 'POST'])
@api.param('notebook', 'path to the resource on S3')
class RunNotebook(Resource):

    @api.doc(params={'template': 'name of a template to use to store the resulting notebook',
                     'outputNotebookPath': 'path to store the output notebook'})
    @get_path
    def get(self, out_path, out_name, notebook):

        data = dict(request.args)

        try:
            if "template" in data and "outputNotebookPath" in data:
                raise InvalidUsage("either 'outputNotebookPath' or 'template' is supported not both")
        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        default = get_default_template()

        template = None

        try:
            template = data.get("template", default.template.name)
        except:
            pass


        # override default output path
        out_path = data.get("outputNotebookPath", out_path)

        if template:
            template_args = {}
            template_args.update({"notebook_name": out_name})

            try:
                out_path = render(template, template_args=template_args)
            except NoResultFound as error:
                response = Response(json.dumps({"error": "No template: " + template}))
                response.status_code = 404
                return response

        if "s3://" not in out_path:
            try:
                os.makedirs(out_path, mode=0o777, exist_ok=False)
            except:
                # directory exists
                pass

        outfile = os.path.join(out_path, out_name)


        try:
            result = pm.execute_notebook(
                "s3://" + notebook,
                outfile,
                parameters=data
            )

        except ClientError as error:
            response = Response(json.dumps(error.response["Error"]))
            response.status_code = int(error.response["Error"]["Code"])
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

    @run.expect(run_post_model)
    @get_path
    def post(self, out_path, out_name, notebook):

        if request.get_json(force=True):

            data = request.get_json()

            # parameters sent to notebook
            parameters = data.get("parameters", None)

            try:
                if "template" in data and "outputNotebookPath" in data:
                    raise InvalidUsage("either 'outputNotebookPath' or 'template' is supported not both")
            except InvalidUsage as error:
                response = Response(json.dumps(error.to_dict()))
                response.status_code = error.status_code
                return response

            template = data.get("template", get_default_template().template if get_default_template() else None)
            out_path = data.get("outputNotebookPath", out_path)

            if template:
                template_args = {}
                template_args.update(template.get("args", {}))
                template_args.update({"notebook_name": out_name})
                out_path = render(template["name"], template_args=template_args)

        else:
            raise InvalidUsage("only application/json supported")

        if "s3://" not in out_path:
            try:
                os.makedirs(out_path, mode=0o777, exist_ok=False)
            except:
                # directory exists
                pass

        outfile = os.path.join(out_path, out_name)

        result = pm.execute_notebook(
            "s3://" + notebook,
            outfile,
            parameters=parameters
        )

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


templates_ns = api.namespace('templates', description='For defining and retrieving templates')
# gets and sets the template which is default.

templates_post_model = templates_ns.model('template_post', {
                                     "name": fields.String,
                                     "content": fields.String,
                                     "default": fields.String(enum=["true", "false", "t", "f", "yes", "no", "y", "n",
                                                                    "on", "off", "0", "1"],
                                                              description="a string representing a truth value")
                                }
                         )


@templates_ns.route('/', methods=['GET', 'POST'])
class TemplatesRoutes(Resource):
    @api.param('default', 'set as default template',
               enum=["true", "false", "t", "f", "yes", "no", "y", "n", "on", "off", "0", "1"])
    def get(self):

        if "default" in request.args:
            return jsonify(get_default_template().template.as_dict() or [])
        else:
            return list_templates()

    @templates_ns.expect(templates_post_model)
    def post(self):

        data = json.loads(request.data.decode())

        existing = Template.query.filter_by(name=data["name"])

        if existing.first():
            if "content" in data:
                existing.update(dict(content=data["content"]))
                sadb.session.commit()
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
                dt.template_id = existing.first().id
                save_models([dt])

        else:
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


template_ns = api.namespace('template', description='For defining and retrieving templates')
# gets and sets the template which is default.


# gets and sets templates with url parameters
@template_ns.route('/<path:template>', methods=['GET', 'POST', 'DELETE'])
class TemplateRoutes(Resource):
    def get(self, template):

        response = result_to_dicts(Template.query.filter_by(name=template))

        return jsonify(response)

    def delete(self, template):

        template = Template.query.filter_by(name=template).first()
        sadb.session.delete(template)
        sadb.session.commit()

        return jsonify(result_to_dicts([template]))

    def post(self, template):

        data = json.loads(request.data.decode())

        existing = Template.query.filter_by(name=template)

        if existing.first():
            existing.update(dict(content=data["content"]))
            sadb.session.commit()
            if strtobool(data.get('default') or "false"):
                dt = DefaultTemplate.query.one()
                dt.template_id = existing.first().id
                save_models([dt])

        else:
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


# renders the template stored in the databse
def render(template_name, template_args={}):

    # some initial default args for things like a time stamp.
    template_args["timestamp"] = time.strftime("%Y%m%d%H%M%S")
    template_args["year"] = time.strftime("%Y")
    template_args["month"] = time.strftime("%m")
    template_args["day"] = time.strftime("%d")

    t = Template.query.filter_by(name=template_name).one()

    rendered_template = render_template_string(t.content, args=template_args)

    return rendered_template
