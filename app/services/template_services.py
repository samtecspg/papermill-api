from app import db as sadb
from app.models import DefaultTemplate, Template


def result_to_dicts(result_rows):
    result = []
    for each in result_rows:
        result.append(each.as_dict())
    return result


def delete(name):
    template = Template.query.filter_by(name=name).first()
    sadb.session.delete(template)
    sadb.session.commit()


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
