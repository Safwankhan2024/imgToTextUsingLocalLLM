from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('chapter/<int:chapter_id>/', views.chapter_detail, name='chapter_detail'),
    path('chapter/<int:chapter_id>/upload/', views.upload_images, name='upload_images'),
    path('chapter/<int:chapter_id>/reorder/', views.reorder_pages, name='reorder_pages'),
    path('chapter/<int:chapter_id>/extract/', views.trigger_extraction, name='trigger_extraction'),
    path('chapter/<int:chapter_id>/page-list-status/', views.page_list_status, name='page_list_status'),
    path('chapter/<int:chapter_id>/review/', views.review_extracted, name='review_extracted'),
    path('lookup-years/', views.title_year_lookup, name='title_year_lookup'),
    path('lookup-years/<uuid:task_id>/status/', views.title_lookup_status, name='title_lookup_status'),
    path('lookup-years/<uuid:task_id>/cancel/', views.cancel_title_lookup, name='cancel_title_lookup'),
    path('templates/create/', views.template_create, name='template_create'),
    path('templates/<int:template_id>/edit/', views.template_edit_form, name='template_edit_form'),
    path('templates/<int:template_id>/update/', views.template_update, name='template_update'),
    path('templates/<int:template_id>/delete/', views.template_delete, name='template_delete'),
]