from django.views import View
from django.shortcuts import render

class BaseTemplateSmokeTest(View):
    def get(self, request):
        # Renderiza directamente la plantilla global base.html
        return render(request, "base.html")
