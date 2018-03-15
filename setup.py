import pathlib

from setuptools import setup, find_packages

CONFIGDIR = pathlib.Path.home() / '.config' / 'alarm'
CONFIGDIR.mkdir(parents=True, exist_ok=True)

with open('gradual/__init__.py', 'r') as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.strip().split('=')[1].strip(' \'"')
            break
    else:
        version = '0.0.1'

with open('README.rst', 'rb') as f:
    readme = f.read().decode('utf-8')

REQUIRES = [
    'spfy',
    'kick',
    'first',
    'fire',
    'requests',
    'backoff',
    'python-dateutil',
    'hug',
    'pony',
    'zeroconf',
    'astral',
]

setup(
    name='gradual',
    version=version,
    description='Gradual alarm with Spotify Connect',
    long_description=readme,
    author='Alin Panaitiu',
    author_email='alin.p32@gmail.com',
    maintainer='Alin Panaitiu',
    maintainer_email='alin.p32@gmail.com',
    url='https://github.com/alin23/gradual-python',
    license='MIT/Apache-2.0',
    keywords=[
        '',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ],
    dependency_links=[
        'git+https://github.com/alin23/spotipy.git@connect'
    ],
    install_requires=REQUIRES,
    tests_require=['coverage', 'pytest'],
    packages=find_packages(),
    package_data={
        'gradual': [
            'config/config.toml'
        ]
    },
    entry_points={
        'console_scripts': ['alarm = gradual.alarm:main']
    },
    data_files=[
        (str(CONFIGDIR), ['gradual/config/config.toml'])
    ],
    zip_safe=False
)
