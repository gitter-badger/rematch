import os
from setuptools import setup, find_packages

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(fname).read()

def get_version(ppath):
    context = {}
    execfile(os.path.join(ppath, 'version.py'), context)
    return context['__version__']

def find_packages_relative(base):
    return [base] + [os.path.join(base, package)
             for package in find_packages(base)]

def build_setup(name, version_path, package_base, package_data):
  setup(
    name = name,
    version = get_version(version_path),
    author = "Nir Izraeli",
    author_email = "nirizr@gmail.com",
    description = ("A IDA Pro plugin and server framework for binary function "
                   "level diffing."),
    keywords = ["rematch", "ida", "idapro", "bindiff", "binary diffing",
                "reverse engineering"],
    url = "https://www.github.com/nirizr/rematch/",
    packages=find_packages_relative(package_base),
    package_data=package_data,
    long_description=read('README.md'),
    classifiers=[
      "Development Status :: 3 - Alpha",
    ],
  )

