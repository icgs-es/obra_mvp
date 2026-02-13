from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone


@login_required
def dashboard(request):
    hoy = timezone.localdate()
    ahora = timezone.localtime()

    ctx = {
        "hoy": hoy,
        "ahora": ahora,
    }
    return render(request, "portal/index.html", ctx)


@login_required
def app_home(request):
    # Alias por compatibilidad si alguna URL vieja apunta aquí
    return dashboard(request)
