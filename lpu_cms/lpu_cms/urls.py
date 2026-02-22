from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView          # ← add this

urlpatterns = [
    path('admin/',      admin.site.urls),
    path('accounts/',   include('django.contrib.auth.urls')),
    path('attendance/', include('attendance.urls', namespace='attendance')),
    path('',            RedirectView.as_view(url='/accounts/login/')),  # ← add this
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)