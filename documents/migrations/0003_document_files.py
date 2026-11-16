from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_document_version'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='file',
            field=models.FileField(blank=True, null=True, upload_to='documents/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='document',
            name='source_file',
            field=models.FileField(blank=True, null=True, upload_to='imports/%Y/%m/'),
        ),
    ]
