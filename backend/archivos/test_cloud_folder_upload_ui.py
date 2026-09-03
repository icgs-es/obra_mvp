from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import (
    SessionMiddleware,
)
from django.template.loader import (
    get_template,
    render_to_string,
)
from django.test import (
    RequestFactory,
    TestCase,
    override_settings,
)


TEST_STORAGES = deepcopy(
    settings.STORAGES
)

TEST_STORAGES["staticfiles"] = {
    "BACKEND": (
        "django.contrib.staticfiles.storage."
        "StaticFilesStorage"
    ),
}


@override_settings(
    STORAGES=TEST_STORAGES
)
class CloudFolderUploadPreviewUITests(
    TestCase
):
    def setUp(self):
        User = get_user_model()

        self.staff = User.objects.create_user(
            username="p2a_staff",
            password="x",
            is_staff=True,
        )

        self.normal = User.objects.create_user(
            username="p2a_normal",
            password="x",
            is_staff=False,
        )

        self.factory = RequestFactory()

        self.base_dir = Path(
            settings.BASE_DIR
        )

        self.js_path = (
            self.base_dir
            / "archivos"
            / "static"
            / "archivos"
            / "cloud_folder_upload_preview.js"
        )

        self.css_path = (
            self.base_dir
            / "archivos"
            / "static"
            / "archivos"
            / "cloud_folder_upload_preview.css"
        )

        self.partial_path = (
            self.base_dir
            / "archivos"
            / "templates"
            / "archivos"
            / "_cloud_folder_upload_preview.html"
        )

        # P3_TEST_FOLDER_UPLOAD_PERMISSION
        from django.contrib.auth.models import (
            Permission,
        )

        upload_folder_permission = (
            Permission.objects.get(
                content_type__app_label=(
                    "archivos"
                ),
                codename="upload_folder",
            )
        )


        for permission_user in (
            get_user_model()
            .objects
            .filter(is_staff=True)
        ):
            permission_user.user_permissions.add(
                upload_folder_permission
            )

    def request(self, user):
        request = self.factory.get(
            "/app/archivos/?path=TECNICOS",
            secure=True,
        )

        middleware = SessionMiddleware(
            lambda value: None
        )

        middleware.process_request(
            request
        )

        request.session.save()
        request.user = user

        return request

    @staticmethod
    def context():
        return {
            "breadcrumbs": [
                {
                    "name": "Archivos",
                    "url": "/app/archivos/",
                },
                {
                    "name": "TECNICOS",
                    "url": "",
                },
            ],
            "current_path": "TECNICOS",
            "current_name": "TECNICOS",
            "current_url": (
                "/app/archivos/?path=TECNICOS"
            ),
            "parent_path": "",
            "parent_url": "/app/archivos/",
            "items": [],
            "sort_field": "name",
            "sort_direction": "asc",
            "sort_name_url": (
                "/app/archivos/"
                "?path=TECNICOS&sort=name"
            ),
            "sort_date_url": (
                "/app/archivos/"
                "?path=TECNICOS&sort=date"
            ),
            "error": "",
        }

    def render(self, user):
        return render_to_string(
            "archivos/cloud_explorer.html",
            self.context(),
            request=self.request(user),
        )

    def test_templates_cargan(self):
        cloud = get_template(
            "archivos/cloud_explorer.html"
        )

        partial = get_template(
            "archivos/"
            "_cloud_folder_upload_preview.html"
        )

        self.assertTrue(
            cloud.origin.name.endswith(
                "cloud_explorer.html"
            )
        )

        self.assertTrue(
            partial.origin.name.endswith(
                "_cloud_folder_upload_preview.html"
            )
        )

    def test_staff_ve_selector_y_panel(self):
        html = self.render(
            self.staff
        )

        self.assertIn(
            'id="folderUploadChooseButton"',
            html,
        )

        self.assertIn(
            'id="folderUploadInput"',
            html,
        )

        self.assertIn(
            "webkitdirectory",
            html,
        )

        self.assertIn(
            'id="folderUploadPreview"',
            html,
        )

        self.assertIn(
            (
                "/app/archivos/cloud/"
                "folder-upload/preflight/"
            ),
            html,
        )

        self.assertIn(
            'id="folderUploadExecuteButton"',
            html,
        )

        self.assertIn(
            (
                "/app/archivos/cloud/"
                "folder-upload/execute/"
            ),
            html,
        )

    def test_usuario_normal_no_ve_p2a(self):
        html = self.render(
            self.normal
        )

        self.assertNotIn(
            'id="folderUploadChooseButton"',
            html,
        )

        self.assertNotIn(
            'id="folderUploadPreview"',
            html,
        )

    def test_javascript_solo_usa_preflight(self):
        source = self.js_path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "webkitRelativePath",
            source,
        )

        self.assertIn(
            "fetch(",
            source,
        )

        self.assertIn(
            "preflightUrl",
            source,
        )

        self.assertNotIn(
            "folder-upload/execute",
            source,
        )

        self.assertNotIn(
            "FormData(",
            source,
        )

        self.assertIn(
            "executeButton.disabled = true",
            source,
        )

    def test_estaticos_y_partial_existen(self):
        self.assertTrue(
            self.js_path.is_file()
        )

        self.assertTrue(
            self.css_path.is_file()
        )

        self.assertTrue(
            self.partial_path.is_file()
        )
