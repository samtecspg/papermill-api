import json
import os
import time
from distutils.util import strtobool

import papermill as pm
import scrapbook as sb
# TODO: decouple the flask from this service
from flask import request, Response, render_template_string, abort
from sqlalchemy.orm.exc import NoResultFound

import app.services.template_services as ts
from app.main.errors import InvalidUsage
from app.models import Template


def result_to_dicts(result_rows):
    result = []
    for each in result_rows:
        result.append(each.as_dict())
    return result


def default_template_parameters(f):
    def wrapper(template_name, default, user_out, output_path, template_args):
        # some initial default args for things like a time stamp.
        template_args["timestamp"] = time.strftime("%Y%m%d%H%M%S")
        template_args["year"] = time.strftime("%Y")
        template_args["month"] = time.strftime("%m")
        template_args["day"] = time.strftime("%d")
        return f(template_name, default, user_out, output_path, template_args=template_args)

    return wrapper


def execute_notebook(out_path, parameters, paths_dict):
    # TODO this leaves an empty directory if 'execute_notebook' is unsuccessful
    if "s3://" not in out_path:
        try:
            os.makedirs(out_path, mode=0o777, exist_ok=False)
        except:
            # directory exists
            pass
    outfile = os.path.join(out_path, paths_dict["out_notebook_name"])
    result = pm.execute_notebook(
        paths_dict["in_notebook"],
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


@default_template_parameters
# if the user specifies a template, render the template
# if the user specifies an output path, render that
# if neither of these are defined, render the default template
# If the default template does not exist, use the location of the input notebook
def render(template_name, default, user_out, output_path, template_args={}):
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
        rendered_template = render_template_string(output_path, args=template_args)

    return rendered_template


def run_notebook(data, paths_dict):
    default = ts.get_default_template()
    template = data.get("template", None)
    template_args = {}
    template_args.update({"notebook_name": paths_dict["out_notebook_name"]})
    out_path = render(template, default, paths_dict["user_out"], paths_dict["out_path"], template_args=template_args)
    return out_path


def get(paths_dict, data):
    out_path = run_notebook(data, paths_dict)
    return execute_notebook(out_path, parameters=data, paths_dict=paths_dict)


def post(paths_dict, data):
    if "template" in data and "outputNotebookPath" in data:
        raise InvalidUsage("either 'outputNotebookPath' or 'template' is supported not both")

    parameters = data.get("parameters", None)
    out_path = run_notebook(data, paths_dict)
    return execute_notebook(out_path, parameters, paths_dict)
