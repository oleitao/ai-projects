# Generated manually for initial project scaffold.
from __future__ import annotations

import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="ChatSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("source_type", models.CharField(choices=[("pdf_upload", "PDF upload"), ("pdf_local", "PDF local"), ("url", "URL")], max_length=20)),
                ("source_uri", models.TextField()),
                ("title", models.CharField(blank=True, max_length=512)),
                ("checksum", models.CharField(blank=True, max_length=64)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("queued", "queued"), ("processing", "processing"), ("done", "done"), ("failed", "failed")], default="queued", max_length=20)),
                ("error", models.TextField(blank=True)),
                ("uploaded_file", models.FileField(blank=True, null=True, upload_to="uploads/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Chunk",
            fields=[
                ("id", models.CharField(max_length=128, primary_key=True, serialize=False)),
                ("chunk_index", models.PositiveIntegerField()),
                ("text", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="ragapp.document",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("document", "chunk_index"), name="uniq_document_chunk_index"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Embedding",
            fields=[
                (
                    "chunk",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to="ragapp.chunk",
                    ),
                ),
                ("model", models.CharField(max_length=128)),
                ("dims", models.PositiveIntegerField()),
                ("vector", models.BinaryField()),
                ("norm", models.FloatField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="ChatTurn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.TextField()),
                ("answer", models.TextField()),
                ("citations", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="turns",
                        to="ragapp.chatsession",
                    ),
                ),
            ],
        ),
    ]

