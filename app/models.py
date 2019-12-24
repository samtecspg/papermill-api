from app import db as sadb


class Template(sadb.Model):
    id = sadb.Column(sadb.INT, primary_key=True)
    name = sadb.Column(sadb.String(50), unique=True, nullable=False)
    content = sadb.Column(sadb.TEXT, nullable=False)

    def as_dict(self):
        self_dict = {
            "name": self.name,
            "content": self.content,
        }

        return self_dict

    def __repr__(self):
        return f"Template('{self.name}', '{self.content}')"


class DefaultTemplate(sadb.Model):
    id = sadb.Column(sadb.INT, primary_key=True)
    template_id = sadb.Column(sadb.INT, sadb.ForeignKey('template.id'))
    template = sadb.relationship(
        "Template", backref=sadb.backref("template.name", uselist=False))

    def as_dict(self):
        self_dict = {
            "name": self.template.name if self.template else None,
        }

        return self_dict

    def __repr__(self):
        return f"DefaultTemplate('{self.id}', '{self.template_id}', '{self.template}')"
