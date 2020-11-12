import json
from dataclasses import dataclass
from typing import Sequence, Tuple

from django.contrib.admin.options import BaseModelAdmin
from django.db import models
from django.db.models import OuterRef, Subquery
from django.utils.html import format_html

from .helpers import _get_option
from .types import BaseType, BooleanType, HTMLType
from .util import s


def get_model_name(model, sep="."):
    return f"{model._meta.app_label}{sep}{model.__name__}"


@dataclass
class OrmBoundField:
    field: "OrmBaseField"
    previous: "OrmBoundField"
    full_path: Sequence[str]
    pretty_path: Sequence[str]
    queryset_path: Sequence[str]
    aggregate_clause: Tuple[str, models.Func] = None
    filter_: bool = False
    having: bool = False
    model_name: str = None

    @property
    def path_str(self):
        return s(self.full_path)

    @property
    def queryset_path_str(self):
        return s(self.queryset_path)

    @property
    def group_by(self):
        return self.field.can_pivot

    def _lineage(self):
        if self.previous:
            return self.previous._lineage() + [self]
        return [self]

    def annotate(self, request, qs):
        for field in self._lineage():
            qs = field._annotate(request, qs)
        return qs

    def _annotate(self, request, qs):
        return qs

    def __getattr__(self, name):
        return getattr(self.field, name)

    @classmethod
    def blank(cls):
        return cls(
            field=None, previous=None, full_path=[], pretty_path=[], queryset_path=[]
        )

    def get_format_hints(self, data):
        return self.type_.get_format_hints(self.path_str, data)


@dataclass
class OrmModel:
    fields: dict
    admin: BaseModelAdmin = None

    @property
    def root(self):
        return bool(self.admin)

    @property
    def default_filters(self):
        default_filters = _get_option(self.admin, "default_filters")
        assert isinstance(default_filters, list)
        return [
            (f, l, v if isinstance(v, str) else json.dumps(v))
            for (f, l, v) in default_filters
        ]


@dataclass
class OrmBaseField:
    model_name: str
    name: str
    pretty_name: str
    type_: BaseType = None
    concrete: bool = False
    rel_name: str = None
    can_pivot: bool = False
    choices: Sequence[Tuple[str, str]] = ()

    def __post_init__(self):
        if not self.type_:
            assert self.rel_name
        if self.concrete or self.can_pivot:
            assert self.type_

    def get_formatter(self):
        return self.type_.get_formatter(self.choices)


class OrmFkField(OrmBaseField):
    def __init__(self, model_name, name, pretty_name, rel_name):
        super().__init__(model_name, name, pretty_name, rel_name=rel_name)

    def bind(self, previous):
        previous = previous or OrmBoundField.blank()
        return OrmBoundField(
            field=self,
            previous=previous,
            full_path=previous.full_path + [self.name],
            pretty_path=previous.pretty_path + [self.pretty_name],
            queryset_path=previous.queryset_path + [self.name],
        )


class OrmConcreteField(OrmBaseField):
    def __init__(self, model_name, name, pretty_name, type_, rel_name, choices):
        super().__init__(
            model_name,
            name,
            pretty_name,
            concrete=True,
            type_=type_,
            rel_name=rel_name,
            can_pivot=True,
            choices=choices or (),
        )

    def bind(self, previous):
        previous = previous or OrmBoundField.blank()
        return OrmBoundField(
            field=self,
            previous=previous,
            full_path=previous.full_path + [self.name],
            pretty_path=previous.pretty_path + [self.pretty_name],
            queryset_path=previous.queryset_path + [self.name],
            filter_=True,
        )


class OrmRawField(OrmConcreteField):
    def bind(self, previous):
        return OrmBoundField(
            field=self,
            previous=previous,
            full_path=previous.full_path + [self.name],
            pretty_path=previous.pretty_path + [self.pretty_name],
            queryset_path=previous.queryset_path,
            filter_=True,
        )


class OrmCalculatedField(OrmBaseField):
    def __init__(self, model_name, name, pretty_name, func):
        if getattr(func, "boolean", False):
            type_ = BooleanType
        else:
            type_ = HTMLType

        super().__init__(model_name, name, pretty_name, type_=type_, can_pivot=True)
        self.func = func

    def bind(self, previous):
        previous = previous or OrmBoundField.blank()
        return OrmBoundField(
            field=self,
            previous=previous,
            full_path=previous.full_path + [self.name],
            pretty_path=previous.pretty_path + [self.pretty_name],
            queryset_path=previous.queryset_path + ["id"],
            model_name=self.model_name,
        )

    def get_formatter(self):
        base_formatter = super().get_formatter()

        def format(obj):
            if obj is None:
                return None

            try:
                value = self.func(obj)
            except Exception as e:
                return str(e)

            return base_formatter(value)

        return format


class OrmBoundAnnotatedField(OrmBoundField):
    def _annotate(self, request, qs):
        from .orm_results import admin_get_queryset

        return qs.annotate(
            **{
                s(self.queryset_path): Subquery(
                    admin_get_queryset(self.admin, request, [self.name])
                    .filter(pk=OuterRef(s(self.previous.queryset_path + ["id"])))
                    .values(self.name)[:1],
                    output_field=self.field_type,
                )
            }
        )


class OrmAnnotatedField(OrmBaseField):
    def __init__(
        self, model_name, name, pretty_name, type_, field_type, admin, choices
    ):
        super().__init__(
            model_name,
            name,
            pretty_name,
            type_=type_,
            rel_name=type_.name,
            can_pivot=True,
            concrete=True,
            choices=choices or (),
        )
        self.field_type = field_type
        self.admin = admin

    def bind(self, previous):
        previous = previous or OrmBoundField.blank()

        full_path = previous.full_path + [self.name]
        return OrmBoundAnnotatedField(
            field=self,
            previous=previous,
            full_path=full_path,
            pretty_path=previous.pretty_path + [self.pretty_name],
            queryset_path=[s(["ddb"] + full_path)],
            filter_=True,
        )


class OrmFileField(OrmConcreteField):
    def __init__(self, model_name, name, pretty_name, django_field):
        super().__init__(
            model_name,
            name,
            pretty_name,
            type_=HTMLType,
            rel_name=HTMLType.name,
            choices=None,
        )
        self.django_field = django_field

    def get_formatter(self):
        def format(value):
            if not value:
                return None

            try:
                # some storage backends will hard fail if their underlying storage isn't
                # setup right https://github.com/tolomea/django-data-browser/issues/11
                return format_html(
                    '<a href="{}">{}</a>', self.django_field.storage.url(value), value
                )
            except Exception as e:
                return str(e)

        return format
