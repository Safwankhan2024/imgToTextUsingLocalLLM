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
]