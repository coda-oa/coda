from django.urls import path

from coda.apps.blocklist import views


app_name = "blocklist"
urlpatterns = [
    path("", view=views.blocklist, name="list"),
    path("tab_switch/", view=views.tab_switch, name="tab_switch"),
    path(
        "block_journal/request/<int:pk>/",
        view=views.request_block_journal,
        name="request_block_journal",
    ),
    path("block_journal/<int:pk>/", view=views.block_journal, name="block_journal"),
    path("unblock_journal/<int:pk>/", view=views.unblock_journal, name="unblock_journal"),
    path("confirm_block/<int:pk>/", view=views.confirm_block, name="confirm_block"),
    path(
        "block_publisher/request/<int:pk>/",
        view=views.request_block_publisher,
        name="request_block_publisher",
    ),
    path("block_publisher/<int:pk>/", view=views.block_publisher, name="block_publisher"),
    path("unblock_publisher/<int:pk>/", view=views.unblock_publisher, name="unblock_publisher"),
]
