from setuptools import setup

setup(
    name="face_auth",
    install_requires=[
        "frappe",
        # other core requirements
    ],
    extras_require={
        "face-auth": [
            "dlib>=19.24.0",
            "face-recognition>=1.3.0"
        ]
    }
)