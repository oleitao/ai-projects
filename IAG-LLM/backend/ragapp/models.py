from __future__ import annotations

import uuid

from django.db import models


class Document(models.Model):
    class SourceType(models.TextChoices):
        PDF_UPLOAD = "pdf_upload", "PDF upload"
        PDF_LOCAL = "pdf_local", "PDF local"
        URL = "url", "URL"

    class Status(models.TextChoices):
        QUEUED = "queued", "queued"
        PROCESSING = "processing", "processing"
        DONE = "done", "done"
        FAILED = "failed", "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_uri = models.TextField()
    title = models.CharField(max_length=512, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    tags = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED
    )
    error = models.TextField(blank=True)
    uploaded_file = models.FileField(upload_to="uploads/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Chunk(models.Model):
    id = models.CharField(primary_key=True, max_length=128)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("document", "chunk_index"), name="uniq_document_chunk_index"
            )
        ]


class Embedding(models.Model):
    chunk = models.OneToOneField(Chunk, on_delete=models.CASCADE, primary_key=True)
    model = models.CharField(max_length=128)
    dims = models.PositiveIntegerField()
    vector = models.BinaryField()
    norm = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)


class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ChatTurn(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="turns")
    question = models.TextField()
    answer = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

