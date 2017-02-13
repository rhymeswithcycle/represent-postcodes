from __future__ import unicode_literals

import csv
import logging
import sys

from boundaries.models import BoundarySet, Boundary
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.template.defaultfilters import slugify

from postcodes.models import Postcode, PostcodeConcordance

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """Imports a headerless CSV file with columns for code,term. The term
matches a unique boundary in the boundary set. See --searchfield for details.

The first two arguments to this command must be the slug of a boundary set and a
description of the data source in 30 characters or less.

If no filename is given, reads from standard input."""
    args = '<slug> <source> [<filename>]'

    def add_arguments(self, parser):
        parser.add_argument('--searchfield', action='store', dest='search-field',
            default='external_id',
            help="Set the SQL column to which the second column of the CSV corresponds. One of 'external_id' (default), 'name' or 'slug'.")

    @transaction.atomic
    def handle(self, *args, **options):
        if len(args) < 2:
            raise CommandError("Missing slug and source arguments. See --help.")

        slug = args[0]
        source = args[1]

        if len(args) == 3:
            f = open(args[2])
        else:
            f = sys.stdin

        boundary_set = BoundarySet.objects.get(slug=slug)
        boundaries = Boundary.objects.filter(set=boundary_set)

        # Delete all concordances from this source.
        PostcodeConcordance.objects.filter(source=source).delete()

        boundaries_seen = dict()
        for (code, term) in csv.reader(f):
            try:
                (postcode, created) = Postcode.objects.get_or_create(code=code)
            except ValidationError as e:
                log.error("%s: %r" % (code, e))
                continue

            try:
                boundary = boundaries_seen.get(term)
                if not boundary:
                    if options['search-field'] == 'name':
                        boundary = boundaries.get(slug=slugify(term))
                    else:
                        boundary = boundaries.get(**{options['search-field']: term})
                    boundaries_seen[term] = boundary
            except Boundary.DoesNotExist:
                log.error("No boundary %s matches %s" % (options['search-field'], term))
                continue

            path = '%s/%s' % (boundary_set.slug, boundary.slug)
            if PostcodeConcordance.objects.filter(code=postcode, boundary=path).exists():
                log.warning("Concordance already exists between %s and %s" % (code, path))
                continue

            PostcodeConcordance.objects.create(
                code=postcode,
                boundary=path,
                source=source,
            )
