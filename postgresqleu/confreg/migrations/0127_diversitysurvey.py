# Generated for the diversity survey feature.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('confreg', '0126_visaletter'),
    ]

    operations = [
        migrations.AddField(
            model_name='conference',
            name='diversity_survey_enabled',
            field=models.BooleanField(default=False, help_text='Offer attendees an anonymous demographic survey after registering', verbose_name='Diversity survey'),
        ),
        migrations.AddField(
            model_name='conferenceregistration',
            name='diversity_survey_response',
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
        migrations.CreateModel(
            name='DiversitySurveyAnswer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('age_range', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('18-24', '18-24'), ('25-34', '25-34'), ('35-44', '35-44'), ('45-54', '45-54'), ('55-64', '55-64'), ('65+', '65 or older')], max_length=20, verbose_name='Age range')),
                ('gender_identity', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('woman', 'Woman'), ('man', 'Man'), ('non-binary', 'Non-binary'), ('other', 'Other')], max_length=20, verbose_name='Gender identity')),
                ('ethnicity', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('white', 'White / European descent'), ('asian', 'Asian'), ('black', 'Black / African descent'), ('hispanic', 'Hispanic / Latino'), ('middle-eastern', 'Middle Eastern / North African'), ('mixed', 'Mixed or multiple ethnicities'), ('other', 'Other')], max_length=20, verbose_name='Ethnicity')),
                ('career_level', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('student', 'Student'), ('entry', 'Entry level (0–2 years)'), ('mid', 'Mid level (3–7 years)'), ('senior', 'Senior level (8–15 years)'), ('lead', 'Lead / Principal (15+ years)'), ('management', 'Management'), ('executive', 'Executive'), ('other', 'Other')], max_length=20, verbose_name='Career level')),
                ('years_in_tech', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('0-1', '0–1 years'), ('2-5', '2–5 years'), ('6-10', '6–10 years'), ('11-15', '11–15 years'), ('16-20', '16–20 years'), ('20+', 'More than 20 years')], max_length=10, verbose_name='Years in technology')),
                ('education_level', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('high-school', 'High school'), ('bachelors', "Bachelor's degree"), ('masters', "Master's degree"), ('phd', 'PhD or Doctorate'), ('bootcamp', 'Coding bootcamp'), ('self-taught', 'Self-taught'), ('other', 'Other')], max_length=20, verbose_name='Highest education level')),
                ('company_size', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('1-10', '1–10 employees'), ('11-50', '11–50 employees'), ('51-200', '51–200 employees'), ('201-1000', '201–1000 employees'), ('1000+', 'More than 1000 employees'), ('freelance', 'Freelancer / Consultant'), ('non-profit', 'Non-profit organisation'), ('government', 'Government'), ('academic', 'Academic institution')], max_length=20, verbose_name='Company size')),
                ('first_time_attendee', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('yes', 'Yes'), ('no', 'No')], max_length=3, verbose_name='Is this your first PostgreSQL conference?')),
                ('how_heard', models.CharField(blank=True, choices=[('', 'Prefer not to say'), ('website', 'PostgreSQL website'), ('social-media', 'Social media'), ('colleague', 'Colleague or friend'), ('previous-attendee', 'Previous conference attendee'), ('mailing-list', 'Mailing list'), ('blog', 'Blog or news article'), ('employer', 'Employer'), ('other', 'Other')], max_length=20, verbose_name='How did you hear about this conference?')),
                ('accessibility_needs', models.TextField(blank=True, verbose_name='Accessibility accommodations used (optional)')),
                ('conference', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='confreg.conference')),
            ],
        ),
    ]
