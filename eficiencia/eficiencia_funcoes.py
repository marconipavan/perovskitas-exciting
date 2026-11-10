import pvlib
from scipy import constants as sc

hc = 1239.8419  # Planck's constant * speed of light in eV * nm
hbar_c = hc / (2.0 * np.pi)   # eV nm   (hbar*c) -- needed because E = hbar*omega

def get_sun_spectra():
  """Fetch the reference standard spectra and return energy and irradiance arrays."""
  spectra = pvlib.spectrum.get_reference_spectra(standard='ASTM G173-03')
  wavelength_nm = spectra.index.values          # Wavelengths in nm
  irradiance_nm = spectra['global'].values      # Wavelength irradiance (W/m^2/nm)
  energy_ev = hc / wavelength_nm
  irradiance_ev = irradiance_nm * (wavelength_nm**2) / hc
  # wavelength is a decreasing function of energy -> resort ascending in E
  order = np.argsort(energy_ev)
  E_sun = energy_ev[order]
  I_sun_E = irradiance_ev[order]
  return E_sun, I_sun_E

def get_absorption_coefficient(E, epsilon_real, epsilon_imag):
  """Compute the absorption coefficient alpha(E) from the complex dielectric function."""
  # extinction coefficient kappa(E), dimensionless
  kappa = np.sqrt(0.5 * (np.sqrt(epsilon_real ** 2 + epsilon_imag ** 2) - epsilon_real))
  # absorption coefficient: alpha(E) = 2 E kappa(E) / (hbar c)
  alpha_nm = 2.0 * E * kappa / hbar_c    # nm^-1
  return alpha_nm

def get_dielectric_function(directory):
  """Return the complex dielectric function as a function of energy."""
  base_name = "EPSILON_BSE-singlet-TDA-BAR_SCR-full_OC"
  for i, direction in enumerate(["11", "22", "33"]):
    file_name = f"{directory}/{base_name}{direction}.OUT"
    data = np.loadtxt(file_name, skiprows=18, usecols=(0, 1, 2))
    if i == 0:
      E_bse = data[:, 0]
      epsilon_real_average = np.zeros((len(E_bse)))
      epsilon_imag_average = np.zeros((len(E_bse)))
    epsilon_real_average += data[:, 1]/3.0
    epsilon_imag_average += data[:, 2]/3.0
  return E_bse, epsilon_real_average, epsilon_imag_average

def get_short_circuit_current(E_sun, absorptivity_bse, I_sun_E):
  """Compute the short-circuit current density J_sc [A/m^2]."""
  q = sc.elementary_charge   # C  (numerically equal to J per eV)
  # photon flux from power density -> divide by photon energy [J]
  phi_sun = I_sun_E / (E_sun * q)     # photons s^-1 m^-2 eV^-1
  # Short-circuit current density: J_sc = q * integral(A(E) * phi(E) dE)
  J_sc = q * np.trapezoid(absorptivity_bse * phi_sun, E_sun)      # A/m^2
  return J_sc

def bb_photon_flux(E, T):
  """Planck spectral photon radiance: photons s^-1 m^-2 eV^-1 sr^-1.

  Handles E -> 0 explicitly: the physical limit is 0 (photon flux
  vanishes at zero energy), but the literal formula gives 0/0 there,
  and np.expm1 avoids catastrophic cancellation for small E/kT.
  """
  h_eV = sc.h / sc.e     # eV s
  c = sc.c               # m/s
  kB_eV = sc.k / sc.e    # eV/K

  E = np.asarray(E, dtype=float)
  flux = np.zeros_like(E)

  nonzero = E > 0
  x = E[nonzero] / (kB_eV * T)
  flux[nonzero] = 2.0 * E[nonzero] ** 2 / (h_eV ** 3 * c ** 2 * np.expm1(x))

  return flux

def get_radiative_reverse_saturation_current(E_bse, absorptivity_bse, T, points_per_kT=20):
  """Compute the reverse saturation current density J_0 [A/m^2]."""
  q = sc.elementary_charge
  kB_eV = sc.k / sc.e

  # PCHIP is shape-preserving: it will not overshoot below the data's
  # min or above its max, unlike a cubic spline -- important right at
  # a sharp rising edge sampled by a coarse mesh.
  from scipy.interpolate import PchipInterpolator
  A_interp = PchipInterpolator(E_bse, absorptivity_bse, extrapolate=False)

  # fine grid: resolve kB*T with `points_per_kT` points
  dE_fine = (kB_eV * T) / points_per_kT
  n_points = int((E_bse.max() - E_bse.min()) / dE_fine)
  E_fine = np.linspace(E_bse.min(), E_bse.max(), n_points)

  A_fine = np.nan_to_num(A_interp(E_fine), nan=0.0)
  A_fine = np.clip(A_fine, 0.0, 1.0)   # belt-and-suspenders: absorptance must be in [0,1]

  I_bb_fine = bb_photon_flux(E_fine, T)
  J0_rad = q * np.pi * np.trapezoid(A_fine * I_bb_fine, E_fine)
  return J0_rad

def obtain_gaps(eigval_file):
  Ha = 27.211396132
  with open(eigval_file, 'r') as f:
    lines = f.readlines()
  n_kpts = int(lines[0].split()[0])
  n_bands = int(lines[1].split()[0])
  idx_start = 2
  eigenvalues = np.zeros((n_kpts, n_bands))
  occupations = np.zeros((n_kpts, n_bands))
  i_lines = idx_start
  for k in range(n_kpts):
    i_lines += 3
    for b in range(n_bands):
      line = lines[i_lines]
      eigenvalues[k, b] = float(line.split()[1])
      occupations[k, b] = float(line.split()[2])
      i_lines += 1
    i_lines += 1
  threshold = 1e-4
  occupied_mask   = occupations > threshold
  unoccupied_mask = occupations < threshold
  vbm = np.max(np.where(occupied_mask,   eigenvalues, -np.inf), axis=1)
  cbm = np.min(np.where(unoccupied_mask, eigenvalues,  np.inf), axis=1)
  direct_gaps = cbm - vbm
  return (np.min(cbm)-np.max(vbm))*Ha, np.min(direct_gaps)*Ha
