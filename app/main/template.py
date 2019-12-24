import json
from distutils.util import strtobool

from flask import jsonify, Response, request
from flask_restplus import Resource

import app.services.template_services as ts
from app import db as sadb
from app.main.errors import InvalidUsage
from app.main.views import template_ns, result_to_dicts, templates_ns, templates_post_model, save_models
from app.models import Template, DefaultTemplate


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

        return ts.list_templates()

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

        return ts.list_templates()
