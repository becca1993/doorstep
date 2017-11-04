from setuptools import setup, find_packages

cmdclass = {}
try:
    from babel.messages import frontend as babel
    cmdclass.update({
        'compile_catalog': babel.compile_catalog,
        'extract_messages': babel.extract_messages,
        'init_catalog': babel.init_catalog,
        'update_catalog': babel.update_catalog,
    })
except ImportError as e:
    pass

setup(
    name='ltldoorstep',
    version='0.0.1',
    description='Doorstep: Project Lintol validation engine',
    url='https://github.com/lintol/doorstep',
    author='Project Lintol team (on behalf of)',
    author_email='help@lintol.io',
    license='MIT',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5'
    ],
    keywords='validation lintol data',
    setup_requires=['pytest-runner'],
    extras_require={
        'babel-commands': ['Babel']
    },
    install_requires=[
        'Click',
        'colorama',
        'dask',
        'distributed',
        'tabulate',
        'flask',
        'flask_restful',
        'unicodeblock',
        'goodtables',
        'pypachy',
        'pandas'
    ],
    include_package_data=True,
    tests_require=['pytest'],
    entry_points='''
        [console_scripts]
        ltldoorstep=ltldoorstep.scripts.ltldoorstep:cli
    ''',
    cmdclass=cmdclass
)