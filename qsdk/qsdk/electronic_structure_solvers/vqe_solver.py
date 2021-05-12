"""
Implements the variational quantum eigensolver (VQE) algorithm to solve electronic structure calculations.
"""

from enum import Enum
import numpy as np
from copy import deepcopy

from agnostic_simulator import Simulator
from qsdk.toolboxes.operators import count_qubits
from qsdk.toolboxes.molecular_computation.molecular_data import MolecularData
from qsdk.toolboxes.molecular_computation.integral_calculation import prepare_mf_RHF
from qsdk.toolboxes.qubit_mappings.mapping_transform import fermion_to_qubit_mapping
from qsdk.toolboxes.ansatz_generator.ansatz import Ansatz
from qsdk.toolboxes.ansatz_generator.uccsd import UCCSD
from qsdk.toolboxes.ansatz_generator.rucc import RUCC


class Ansatze(Enum):
    """ Enumeration of the ansatz circuits supported by VQE"""
    UCCSD = 0
    UCC1 = 1
    UCC3 = 2

class VQESolver:
    """ Solve the electronic structure problem for a molecular system by using the
    variational quantum eigensolver (VQE) algorithm.

    This algorithm evaluates the energy of a molecular system by performing classical optimization
    over a parametrized ansatz circuit.

    Users must first set the desired options of the VQESolver object through the __init__ method, and call the "build"
    method to build the underlying objects (mean-field, hardware backend, ansatz...).
    They are then able to call any of the energy_estimation, simulate, or get_rdm methods.
    In particular, simulate runs the VQE algorithm, returning the optimal energy found by the classical optimizer.

    Attributes:
        molecule (MolecularData) : the molecular system
        mean-field (optional) : mean-field of molecular system
        frozen_orbitals (list[int]): a list of indices for frozen orbitals, reflected in mean-field computation
        qubit_mapping (str) : one of the supported qubit mapping identifiers
        ansatz (Ansatze) : one of the supported ansatze
        optimizer (function handle): a function defining the classical optimizer and its behavior
        initial_var_params (str or array-like) : initial value for the classical optimizer
        backend_options (dict) : parameters to build the Simulator class (see documentation of agnostic_simulator)
        up_then_down (bool): change basis ordering putting all spin up orbitals first, followed by all spin down
            Default, False has alternating spin up/down ordering.
        verbose (bool) : Flag for verbosity of VQE
    """

    def __init__(self, opt_dict):

        default_backend_options = {"target": "qulacs", "n_shots": None, "noise_model": None}
        default_options = {"molecule": None, "mean_field": None, "frozen_orbitals": list(),
                           "qubit_mapping": "jw", "ansatz": Ansatze.UCCSD,
                           "optimizer": self._default_optimizer,
                           "initial_var_params": None,
                           "backend_options": default_backend_options,
                           "up_then_down": False,
                           "verbose": False}

        # Initialize with default values
        self.__dict__ = default_options
        # Overwrite default values with user-provided ones, if they correspond to a valid keyword
        for k, v in opt_dict.items():
            if k in default_options:
                setattr(self, k, v)
            else:
                raise KeyError(f"Keyword :: {k}, not available in VQESolver")

        # Raise error/warnings if input is not as expected
        if not self.molecule:
            raise ValueError(f"A molecule object must be provided when instantiating VQESolver")

        self.optimal_energy = None
        self.optimal_var_params = None
        self.builtin_ansatze = set(Ansatze)

    def build(self):
        """ Build the underlying objects required to run the VQE algorithm afterwards """

        # Build adequate mean-field (RHF for now, others in future).
        if not self.mean_field:
            self.mean_field = prepare_mf_RHF(self.molecule)

        # Compute qubit hamiltonian for the input molecular system
        self.qemist_molecule = MolecularData(self.molecule, self.mean_field, self.frozen_orbitals)
        self.fermionic_hamiltonian = self.qemist_molecule.get_molecular_hamiltonian()
        self.qubit_hamiltonian = fermion_to_qubit_mapping(fermion_operator=self.fermionic_hamiltonian, 
                                                          mapping=self.qubit_mapping,
                                                          n_spinorbitals=self.qemist_molecule.n_qubits,
                                                          n_electrons=self.qemist_molecule.n_electrons,
                                                          up_then_down=self.up_then_down)

        # Verification of system compatibility with UCC1 or UCC3 circuits.
        if self.ansatz in [Ansatze.UCC1, Ansatze.UCC3]:
            # Mapping should be JW because those ansatz are chemically inspired.
            if self.qubit_mapping != "jw":
                raise ValueError("Qubit mapping must be JW for {} ansatz.".format(self.ansatz))
            # They are encoded with this convention.
            if not self.up_then_down:
                raise ValueError("Parameter up_then_down must be set to True for {} ansatz.".format(self.ansatz))
            # Only HOMO-LUMO systems are relevant.
            if count_qubits(self.qubit_hamiltonian) != 4:
                raise ValueError("The system must be reduced to a HOMO-LUMO problem for {} ansatz.".format(self.ansatz))

        # Build / set ansatz circuit. Use user-provided circuit or built-in ansatz depending on user input.
        if type(self.ansatz) == Ansatze:
            if self.ansatz == Ansatze.UCCSD:
                self.ansatz = UCCSD(self.qemist_molecule, self.qubit_mapping, self.mean_field, self.up_then_down)
            elif self.ansatz == Ansatze.UCC1:
                self.ansatz = RUCC(1)
            elif self.ansatz == Ansatze.UCC3:
                self.ansatz = RUCC(3)
            else:
                raise ValueError(f"Unsupported ansatz. Built-in ansatze:\n\t{self.builtin_ansatze}")
        elif not isinstance(self.ansatz, Ansatz):
            raise TypeError(f"Invalid ansatz dataype. Expecting instance of Ansatz class, or one of built-in options:\n\t{self.builtin_ansatze}")
        # Set ansatz initial parameters (default or use input), build corresponding ansatz circuit
        self.initial_var_params = self.ansatz.set_var_params(self.initial_var_params)
        self.ansatz.build_circuit()

        # Quantum circuit simulation backend options
        self.backend = Simulator(target=self.backend_options["target"], n_shots=self.backend_options["n_shots"],
                                 noise_model=self.backend_options["noise_model"])

    def simulate(self):
        """ Run the VQE algorithm, using the ansatz, classical optimizer, initial parameters and
         hardware backend built in the build method """
        if not (self.ansatz and self.backend):
            raise RuntimeError("No ansatz circuit or hardware backend built. Have you called VQESolver.build ?")
        return self.optimizer(self.energy_estimation, self.initial_var_params)

    def get_resources(self):
        """ Estimate the resources required by VQE, with the current ansatz. This assumes "build" has been run,
         as it requires the ansatz circuit and the qubit Hamiltonian. Return information that pertains to the user,
          for the purpose of running an experiment on a classical simulator or a quantum device """

        resources = dict()
        resources["qubit_hamiltonian_terms"] = len(self.qubit_hamiltonian.terms)
        resources["circuit_width"] = self.ansatz.circuit.width
        resources["circuit_gates"] = self.ansatz.circuit.size
        resources["circuit_2qubit_gates"] = self.ansatz.circuit.counts['CNOT']  # For now, only CNOTs supported
        resources["circuit_var_gates"] = len(self.ansatz.circuit._variational_gates)
        resources["vqe_variational_parameters"] = len(self.initial_var_params)
        return resources

    def energy_estimation(self, var_params):
        """ Estimate energy using the given ansatz, qubit hamiltonian and compute backend.
         Keeps track of optimal energy and variational parameters along the way

        Args:
             var_params (numpy.array or list): variational parameters to use for VQE energy evaluation
        Returns:
             energy (float): energy computed by VQE using the ansatz and input variational parameters
        """

        # Update variational parameters, compute energy using the hardware backend
        self.ansatz.update_var_params(np.array(var_params))
        energy = self.backend.get_expectation_value(self.qubit_hamiltonian, self.ansatz.circuit)

        if self.verbose:
            print(f"\tEnergy = {energy:.7f} ")

        return energy

    def get_rdm(self, var_params):
        """ Compute the 1- and 2- RDM matrices using the VQE energy evaluation. This method allows
        to combine the DMET problem decomposition technique with the VQE as an electronic structure solver.
         The RDMs are computed by using each fermionic Hamiltonian term, transforming them and computing
         the elements one-by-one.
         Note that the Hamiltonian coefficients will not be multiplied as in the energy evaluation.
         The first element of the Hamiltonian is the nuclear repulsion energy term,
         not the Hamiltonian term.

         Args:
             var_params (numpy.array or list): variational parameters to use for VQE energy evaluation
         Returns:
             (numpy.array, numpy.array): One & two-particle RDMs (rdm1_np & rdm2_np, float64).
         """

        # Save our accurate hamiltonian
        tmp_hamiltonian = self.qubit_hamiltonian

        # Initialize the RDM arrays
        n_mol_orbitals = len(self.ansatz.mf.mo_energy)
        rdm1_np = np.zeros((n_mol_orbitals,) * 2)
        rdm2_np = np.zeros((n_mol_orbitals,) * 4)

        # Lookup "dictionary" (lists are used because keys are non-hashable) to avoid redundant computation
        lookup_ham, lookup_val = list(), list()

        # Loop over each element of Hamiltonian (non-zero value)
        for ikey, key in enumerate(self.fermionic_hamiltonian):
            length = len(key)
            # Ignore constant / empty term
            if not key:
                continue
            # Assign indices depending on one- or two-body term
            if (length == 2):
                iele, jele = (int(ele[0]) // 2 for ele in tuple(key[0:2]))
            elif (length == 4):
                iele, jele, kele, lele = (int(ele[0]) // 2 for ele in tuple(key[0:4]))

            # Select the Hamiltonian element (Set coefficient to one)
            hamiltonian_temp = deepcopy(self.fermionic_hamiltonian)
            for key2 in hamiltonian_temp:
                hamiltonian_temp[key2] = 1. if (key == key2 and ikey != 0) else 0.

            # Obtain qubit Hamiltonian
            qubit_hamiltonian2 =fermion_to_qubit_mapping(fermion_operator=hamiltonian_temp,
                                                         mapping=self.qubit_mapping,
                                                         n_spinorbitals=self.qemist_molecule.n_qubits,
                                                         n_electrons=self.qemist_molecule.n_electrons,
                                                         up_then_down=self.up_then_down)
            qubit_hamiltonian2.compress()

            if qubit_hamiltonian2.terms in lookup_ham:
                opt_energy2 = lookup_val[lookup_ham.index(qubit_hamiltonian2.terms)]
            else:
                # Overwrite with the temp hamiltonian, use it to calculate the energy, store in lookup lists
                self.qubit_hamiltonian = qubit_hamiltonian2
                opt_energy2 = self.energy_estimation(var_params)
                lookup_ham.append(qubit_hamiltonian2.terms)
                lookup_val.append(opt_energy2)

            # Put the values in np arrays (differentiate 1- and 2-RDM)
            if length == 2:
                rdm1_np[iele, jele] += opt_energy2
            elif length == 4:
                if iele != lele or jele != kele:
                    rdm2_np[lele, iele, kele, jele] += 0.5 * opt_energy2
                    rdm2_np[iele, lele, jele, kele] += 0.5 * opt_energy2
                else:
                    rdm2_np[iele, lele, jele, kele] += opt_energy2

        # Restore the accurate hamiltonian
        self.qubit_hamiltonian = tmp_hamiltonian

        return rdm1_np, rdm2_np

    # TODO: Could this be done better ?
    def _default_optimizer(self, func, var_params):
        """ Function used as a default optimizer for VQE when user does not provide one. Can be used as an example
        for users who wish to provide their custom optimizer.

        Should set the attributes "optimal_var_params" and "optimal_energy" to ensure the outcome of VQE is
        captured at the end of classical optimization, and can be accessed in a standard way.

        Args:
            func (function handle): The function that performs energy estimation.
                This function takes var_params as input and returns a float.
            var_params (list): The variational parameters (float64).
        Returns:
            The optimal energy found by the optimizer
        """

        from scipy.optimize import minimize
        result = minimize(func, var_params, method='SLSQP',
                          options={'disp': True, 'maxiter': 2000, 'eps': 1e-5, 'ftol': 1e-5})

        self.optimal_var_params = result.x
        self.optimal_energy = result.fun

        if self.verbose:
            print(f"\t\tOptimal UCCSD energy: {self.optimal_energy}")
            print(f"\t\tOptimal UCCSD variational parameters: {self.optimal_var_params}")
            print(f"\t\tNumber of Function Evaluations : {result.nfev}")

        return result.fun