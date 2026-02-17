from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from ragapp import api, views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("ingest", views.ingest_page, name="ingest"),
    path("chat", views.chat_page, name="chat"),
    path("api/documents", api.documents_list, name="api_documents_list"),
    path("api/ingest/pdf", api.ingest_pdf, name="api_ingest_pdf"),
    path("api/ingest/url", api.ingest_url, name="api_ingest_url"),
    path("api/ingest/batch", api.ingest_batch, name="api_ingest_batch"),
    path("api/chat/ask", api.chat_ask, name="api_chat_ask"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

