from django.contrib import admin

from .models import ChatSession, ChatTurn, Chunk, Document, Embedding


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "title", "status", "created_at", "updated_at")
    list_filter = ("source_type", "status")
    search_fields = ("title", "source_uri", "checksum")


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "chunk_index")
    search_fields = ("id", "document__id")


@admin.register(Embedding)
class EmbeddingAdmin(admin.ModelAdmin):
    list_display = ("chunk", "model", "dims", "created_at")
    search_fields = ("chunk__id", "model")


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "updated_at")


@admin.register(ChatTurn)
class ChatTurnAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "created_at")
    search_fields = ("session__id",)

