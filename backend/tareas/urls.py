from django.urls import path
from .views import TareaListView, TareaCreateView, TareaUpdateView, TareaKanbanView, api_detail, task_action

app_name = "tareas"

urlpatterns = [
    path("", TareaListView.as_view(), name="list"),
    path("kanban/", TareaKanbanView.as_view(), name="kanban"),
    path("nueva/", TareaCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", TareaUpdateView.as_view(), name="update"),
    path("api/<int:pk>/", api_detail, name="api_detail"),
    path("api/<int:pk>/action/", task_action, name="action"),
]
