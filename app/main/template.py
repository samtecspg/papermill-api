import json
from distutils.util import strtobool

from flask import jsonify, Response, request
from flask_restplus import Resource
from flask_restplus import fields

from app.main.errors import InvalidUsage
from app.main.views import result_to_dicts, api
from app.models import Template
from app.services import template_services as ts

templates_ns = api.namespace('template', description='For defining, retrieving and deleting templates')
# gets and sets the template which is default.

templates_post_model = templates_ns.model('template_post', {
    "name": fields.String,
    "content": fields.String,
    "default": fields.String(
        enum=["true", "false", "t", "f", "yes", "no", "y", "n", "on", "off", "0", "1"],
        description="a string representing a truth value"
    )
})

templates_delete_model = templates_ns.model('template_delete', {
    "name": fields.String
})

template_ns = api.namespace('template', description='For defining and retrieving templates')


@template_ns.route('/<path:template>', methods=['GET', 'DELETE'])
class TemplateRoutes(Resource):
    def get(self, template):

        response = result_to_dicts(Template.query.filter_by(name=template))

        return jsonify(response)

    def delete(self, template):
        try:
            ts.delete(name=template)
        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response
        except ValueError as error:
            message = dict({"Error": str(error)})
            response = Response(json.dumps(message, indent=4), content_type="application/json")
            response.status_code = 500
            return response
        return ts.list_templates()

    @templates_ns.expect(templates_post_model)
    def post(self, template):
        data = json.loads(request.data.decode())
        try:
            ts.post(name=template, content=data["content"], default=data.get('default'))

        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        return ts.list_templates()


@templates_ns.route('/', methods=['GET', 'POST', 'PATCH', 'DELETE'])
class TemplatesRoutes(Resource):
    @api.param('default', 'Return only default template. Otherwise return all templates.',
               enum=["true", "false", "t", "f", "yes", "no", "y", "n", "on", "off", "0", "1"])
    def get(self):

        if strtobool(request.args.get('default') or "false"):
            return jsonify(ts.get_default_template().as_dict() if ts.get_default_template() else [])
        else:
            return ts.list_templates()

    @templates_ns.expect(templates_delete_model)
    def delete(self):
        data = json.loads(request.data.decode())
        try:
            ts.delete(name=data["name"])

        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        return jsonify(ts.list_templates())

    @templates_ns.expect(templates_post_model)
    def post(self):
        data = json.loads(request.data.decode())
        try:
            ts.post(name=data["name"], content=data["content"], default=data.get('default'))

        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response

        except ValueError as error:
            message = dict({"Error": str(error)})
            response = Response(json.dumps(message, indent=4), content_type="application/json")
            response.status_code = 500
            return response
        return ts.list_templates()

    @templates_ns.expect(templates_post_model)
    def patch(self):
        data = json.loads(request.data.decode())
        try:
            ts.patch(name=data["name"], content=data["content"], default=data.get('default'))
        except InvalidUsage as error:
            response = Response(json.dumps(error.to_dict()))
            response.status_code = error.status_code
            return response
        return ts.list_templates()
