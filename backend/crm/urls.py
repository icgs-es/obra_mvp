from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter
from .views import (
    LeadViewSet,
    LeadListView,
    LeadCreateView,
    LeadUpdateView,
    LeadDeleteView,
    ImportLeadsView,
)

app_name = "crm"

router = DefaultRouter()
router.register(r"leads", LeadViewSet, basename="lead")

urlpatterns = [
    path("", views.crm_index, name="index"),
    path("set-active-team/<int:team_id>/", views.set_active_team, name="set_active_team"),
    path("leads/", LeadListView.as_view(), name="lead_list"),
    path("leads/new/", LeadCreateView.as_view(), name="lead_create"),
    path("leads/import/", ImportLeadsView.as_view(), name="lead_import"),
    path("leads/<int:pk>/edit/", LeadUpdateView.as_view(), name="lead_update"),
    path("leads/<int:pk>/delete/", LeadDeleteView.as_view(), name="lead_delete"),
    path("api/", include(router.urls)),
]
