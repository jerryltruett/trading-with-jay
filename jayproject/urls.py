from django.contrib import admin
from django.urls import include, path

urlpatterns = [path("admin/", admin.site.urls), path("", include("community.urls"))]
admin.site.site_header = "Trading with Jay"
admin.site.site_title = "Trading with Jay · Admin"
admin.site.index_title = "Community control room"
