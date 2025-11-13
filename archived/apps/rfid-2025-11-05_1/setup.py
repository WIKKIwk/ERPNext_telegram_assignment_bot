from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in rfid/__init__.py
from rfid import __version__ as version

with open("README.md", encoding="utf-8") as f:
	long_description = f.read()

setup(
	name="rfid",
	version=version,
	description="End-to-end RFID automation for ERPNext",
	long_description=long_description,
	long_description_content_type="text/markdown",
	author="WIKKIwk",
	author_email="opensource@example.com",
	url="https://github.com/WIKKIwk/RFID-for-Impinj-R700",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires,
	classifiers=[
		"Framework :: Frappe",
		"License :: OSI Approved :: MIT License",
		"Programming Language :: Python",
		"Programming Language :: Python :: 3",
	],
)
