from setuptools import find_packages, setup


def read_requirements():
    """Parse requirements from requirements.txt."""
    reqs_path = 'requirements-setup.txt'
    with open(reqs_path, 'r') as f:
        requirements = [line.rstrip() for line in f]
    return requirements


setup(
    name='aldryn-accounts',
    version=__import__('aldryn_accounts').__version__,
    url='http://github.com/aldryn/aldryn-accounts',
    license='BSD',
    platforms=['OS Independent'],
    description='A registration and authentication app for Aldryn and the django CMS Cloud.',
    author='Divio AG',
    author_email='developers@divio.ch',
    packages=find_packages(),
    install_requires=read_requirements(),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP',
    ],
)
