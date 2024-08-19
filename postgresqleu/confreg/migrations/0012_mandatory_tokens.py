# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0011_optout'),
    ]

    operations = [
        migrations.RunSQL(
            """WITH t AS (
  SELECT r.id, string_agg(lpad(to_hex((random() * 255)::int)::text, 2, '0'),'') AS rnd
  FROM confreg_conferenceregistration r CROSS JOIN generate_series(1,32) g(g)
  WHERE r.regtoken IS NULL GROUP BY r.id
)
UPDATE confreg_conferenceregistration rr SET regtoken=rnd FROM t WHERE t.id=rr.id""",
        ),
        migrations.AlterField(
            model_name='conferenceregistration',
            name='regtoken',
            field=models.TextField(unique=True),
        ),
        migrations.RunSQL(
            """WITH t AS (
  SELECT s.id, string_agg(lpad(to_hex((random() * 255)::int)::text, 2, '0'),'') AS rnd
  FROM confreg_speaker s CROSS JOIN generate_series(1,32) g(g)
  WHERE s.speakertoken IS NULL GROUP BY s.id
)
UPDATE confreg_speaker ss SET speakertoken=rnd FROM t WHERE t.id=ss.id""",
        ),
        migrations.AlterField(
            model_name='speaker',
            name='speakertoken',
            field=models.TextField(unique=True),
        ),
    ]
