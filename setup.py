from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()

setup(
    name="pyroutelib3",
    py_modules=["pyroutelib3"],
    license="GPL v3",
    version="1.7.0",
    description="Library for simple routing on OSM data",
    long_description=readme,
    long_description_content_type="text/markdown",
    author="Oliver White",
    maintainer="Mikolaj Kuranowski",
    url="https://github.com/MKuranowski/pyroutelib3",
    keywords="osm routing pyroutelib",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Scientific/Engineering :: GIS",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    packages=find_packages(include=["pyroutelib3", "pyroutelib3.*"]),
    python_requires=">=3.6, <4",
    install_requires=["osmiter>=1.1", "typing_extensions"],
    data_files=["LICENSE.txt", "README.md"],
)
