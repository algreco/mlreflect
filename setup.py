from setuptools import setup, find_packages

with open('requirements.txt') as file:
    requirements = file.readlines()

setup(
    name='mlreflect',
    version='0.15.1',
    author='Alessandro Greco',
    author_email='alessandro.greco@uni-tuebingen.de',
    license='GPL3',
    packages=find_packages(),
    zip_safe=False,
    install_requires=requirements,
    python_requires='>=3.6'
)
