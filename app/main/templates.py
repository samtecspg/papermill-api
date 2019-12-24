import json
from distutils.util import strtobool

from flask import request, jsonify, Response
from flask_restplus import Resource

import app.services.template_services as ts
from app.main.errors import InvalidUsage
from app.main.views import templates_ns, api, templates_delete_model, templates_post_model, save_models
from app.models import Template, DefaultTemplate


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
        ts.delete(name=data["name"])
        return jsonify(ts.list_templates())

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

        return ts.list_templates()

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

        return ts.list_templates()
