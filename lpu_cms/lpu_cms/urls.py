from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/',      admin.site.urls),
    path('accounts/',   include('django.contrib.auth.urls')),
    path('attendance/', include('attendance.urls', namespace='attendance')),
    path('food/',       include('food.urls', namespace='food')),   # ← add this
    path('',            RedirectView.as_view(url='/accounts/login/')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)