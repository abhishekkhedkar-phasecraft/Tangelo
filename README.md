# QEMIST_qSDK

Quantum SDK providing access to the tools developed for quantum chemistry simulation on quantum computers and emulators.

The package provides access to some problem decomposition techniques, electronic structure solvers, as well as the
various toolboxes containing the functionalities necessary to build these workflows, or your own.

It was developed to be compatible with QEMIST Cloud, to seamlessly enable the use of large scale problem decomposition
combined with both classical and quantum electronic structure solvers in the cloud. The package also provides local
problem decomposition techniques, and is designed to support the output of a problem decomposition method performed
through QEMIST Cloud as well.

This package relies on another package used as a submodule, agnostic_simulator, which allows users to target a variety
of compute backends (QPUs and simulators) available on their local machine or through cloud services.


## Contents of the repository

Details the organization of this repository and the contents of each folder

- **qsdk** :
Code implementing various functionalities and algorithms to research and perform quantum chemistry experiments on
  gate-model quantum computers or simulators. The various features are exposed in toolboxes, and can be assembled to
  form workflows: electronic structure solvers.

- **agnostic_simulator** :
Code of backend-agnostic quantum circuit simulation submodule
  
- **cont_integration** :
Files related to continuous integration (automated testing, Github workflow)

- **docs** :
Source code documentation and user documentation (readthedocs)

- **examples** :
Examples and tutorials to learn how to use the different functionalities of the package
  

## Install

### Using setuptools

This package can be installed by first cloning this repository with `git clone`, and then retrieving the latest code 
for the `agnostic_simulator` git submodule by performing the following command lines:
```
git submodule init
git submodule update
```

The following assumes you have a terminal open in the root folder of the `qSDK` package.

First, install `agnostic_simulator` using the setuptools by entering the following command lines:
```
cd ./agnostic_simulator
python setup.py install
cd ..
```

For all information regarding `agnostic_simulator`, we recommend you check the code and documentation available in
its dedicated repository: https://github.com/1QB-Information-Technologies/agnostic_simulator

Now, `agnostic_simulator` should be part of the installed modules in your environment. You can then install `qSDK`
by using the setuptools again, with the `setup.py` file present in the `qSDK` root directory:
```
python setup.py install
```

> :warning: If you are using MacOS, your C/C++ compiler may be Clang, which does not support compilation of OpenMP
> multithreaded code. As a consequence, you may encounters errors, or see noticeable degradation in performance for some
> of the dependencies of this package. We recommend you install a suitable alternative (for example, the GNU gcc compiler)
> and then set the CC variable environment to the path to that compiler, before running the setup.py script. You may
> unset the CC environment variable afterwards, as you see fit.

> :warning: During this setup, you may encounter errors, as sometimes the Python package dependencies are installed in 
> an order that does not seem to work out. Frequently, installing the package triggering the error by itself before reattempting
> the command that failed seemed to solve these issues (often observed with `pybind11` and `pyscf`).

If you do not wish to use the code in `qSDK` or `agnostic_simulator` as python modules but want to manipulate and 
access this code directly, you can also remove them from your environment (through the `uninstall` command of pip or conda), 
and simply add the path to the root directory of `qSDK` to the beginning of your `PYTHONPATH` environment variable.

### Using Docker

TODO: validate dockerfile.

## Tests

Unit tests can be found in the `tests` folders, located in the various toolboxes they are related to. To automatically
find and run tests (assuming you are in the `qsdk` subfolder that contains the code of the package):
```
python -m unittest discover
```

## Environment variables

TODO: if any (`agnostic_simulator` has some).
