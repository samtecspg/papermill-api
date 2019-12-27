from distutils.util import strtobool

from app import db as sadb
from app.main.errors import InvalidUsage
from app.main.views import result_to_dicts, save_models
from app.models import DefaultTemplate, Template


def delete(name):
    template = Template.query.filter_by(name=name).first()
    if not template:
        raise InvalidUsage("Template does not exist")
    sadb.session.delete(template)
    sadb.session.commit()


def create(name, content, default):
    existing = Template.query.filter_by(name=name)
    if existing.first():
        raise InvalidUsage("Template exists")
    t = Template(name=name, content=content)
    save_models([t])
    if strtobool(default or "false"):
        try:
            dt = DefaultTemplate.query.one()
        except:
            dt = DefaultTemplate()
        dt.template_id = t.id
        save_models([dt])


def update(name, content, default):
    existing = Template.query.filter_by(name=name).first()
    if not existing:
        raise InvalidUsage("Template does not exist")
    if content:
        existing.content = content
    save_models([existing])
    set_default_template = strtobool(default or "false")
    dt = DefaultTemplate.query.one()
    if set_default_template:
        dt.template_id = existing.id
    # unassign default if is false and this template is currently the default.
    elif dt.template_id == existing.id:
        dt.template_id = None

    save_models([dt])


def list_templates():
    temp = Template.query.all()
    return result_to_dicts(temp)


def get_default_template():
    default = get_default_template_record()
    if not default is None:
        return default.template
    return None


def get_default_template_record():
    return DefaultTemplate.query.first()
