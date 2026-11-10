from scipy import constants as sc
from scipy.interpolate import interp1d
from scipy.optimize import minimize_scalar

def minus_power(V, J_sc, J_0, temperature, kB_eV):
  J = J_sc - J_0 * (np.exp(V / (kB_eV * temperature)) - 1.0)
  return -(J * V)

def smooth_cutoff(E, E_cutoff, width):
    """0 well below E_cutoff, 1 well above it, smooth transition over ~width."""
    return 0.5 * (1.0 + np.tanh((E - E_cutoff) / width))

def kkr_epsilon1(E, eps2):
    """
    Fast Kramers-Kronig transform via FFT-based Hilbert transform.
    O(N log N) instead of O(N^2) -- suitable for N ~ 1e5-1e6 points.

    E: uniform grid, ascending, starting at/near 0.
    eps2: epsilon_2(E) on that grid (apply your cutoff to this beforehand).
    Returns epsilon_1(E) = 1 + Re[KK integral].
    """
    E = np.asarray(E)
    eps2 = np.asarray(eps2)
    N = len(E)

    N_pad = 4 * N                      # zero-padding avoids circular wraparound
    eps2_p = np.zeros(N_pad)
    eps2_p[:N] = eps2

    g = np.concatenate([-eps2_p[::-1][:-1], eps2_p])   # odd extension, g(0)=0

    Ng = len(g)
    freq = np.fft.fftfreq(Ng)
    G = np.fft.fft(g)
    H = 1j * np.sign(freq)
    h = np.fft.ifft(G * H).real

    eps1_full = 1.0 + h
    return eps1_full[N_pad-1 : N_pad-1+N]

fig, ax = plt.subplots(7, 1, figsize=(3, 14), dpi=600)
left = 0.08# the left side of the subplots of the figure
right = 0.97   # the right side of the subplots of the figure
bottom = 0.18  # the bottom of the subplots of the figure
top = 0.97     # the top of the subplots of the figure
wspace = 0.4  # the amount of width reserved for space between subplots,
              # expressed as a fraction of the average axis width
hspace = 0.3  # the amount of height reserved for space between subplots,
              # expressed as a fraction of the average axis height
plt.subplots_adjust(left=left, bottom=bottom, right=right, top=top, wspace=wspace, hspace=hspace)

temperature = 300.0  # temperature [K]
kB_eV = sc.k / sc.e    # eV/K
prefix = home + "/farm/hlrnb/perovskite/calculations/CsPbI3/"
extension = "OUT"
base_name_epsilon = "EPSILON_BSE-singlet-TDA-BAR_SCR-full_OC"
base_name_exciton = "EXCITON_BSE-singlet-TDA-BAR_SCR-full_OC"
epsilon_directory = "EPSILON/"
exciton_directory = "EXCITON/"
DOUBLE_PASS = True
n_pass = 2.0 if DOUBLE_PASS else 1.0
E_sun, I_sun_E = get_sun_spectra()
P_in = np.trapezoid(I_sun_E, E_sun)   # W/m^2 -- should come out close to 1000.37
#E_bse, epsilon_real_average, epsilon_imag_average = get_dielectric_function(prefix + f"/{phase}/bse-dft05-soc-svlo/{epsilon_directory}")
#E_g, E_g_da = obtain_gaps(prefix + f"/{phase}/dft05-soc-svlo/EIGVAL.OUT")
#f_r = np.exp((E_g - E_g_da) / (kB_eV * temperature))
direction = "11"
phases = ["delta", "gamma", "i4mcm", "p4mbm", "pm3m", "r3c", "r3m"]
for i_phase, phase in enumerate(phases):
  filename = f"{prefix}/{phase}/bse-dft05-soc-svlo/{exciton_directory}/{base_name_exciton}{direction}.{extension}"
  energy, oscillator_strength = np.loadtxt(filename, skiprows=14, usecols=(1, 3), max_rows=int(6e5), unpack=True)
  threshold = 1e-2 * np.max(oscillator_strength)
  idx = next(i for i, x in enumerate(oscillator_strength) if x > threshold)
  E_cutoff = energy[idx]
  print(f"Phase = {phase}, E_cutoff = {E_cutoff:.4f} eV")
  E_bse, epsilon_real_average, epsilon_imag_average = get_dielectric_function(prefix + f"/{phase}/bse-dft05-soc-svlo/{epsilon_directory}")
  E_g, E_g_da = obtain_gaps(prefix + f"/{phase}/dft05-soc-svlo/EIGVAL.OUT")
  f_r = np.exp((E_g - E_g_da) / (kB_eV * temperature))
  results = []
  for i_width, width in enumerate([0.05, 0.1, 0.2]):
    cutoff_function = smooth_cutoff(E_bse, E_cutoff, width=width)
    eps_im_filter = cutoff_function * epsilon_imag_average
    eps_re_filter = kkr_epsilon1(E_bse, eps_im_filter)
    alpha_nm = get_absorption_coefficient(E_bse, eps_re_filter, eps_im_filter)
    thicknesses = np.array([1, 5, 10, 50, 100, 500, 1000.0, 5000.0, 1e4])
    efficiencies = np.zeros_like(thicknesses, dtype=float)
    for i, thickness in enumerate(thicknesses):
      A_bse = 1.0 - np.exp(-n_pass * alpha_nm * thickness)   # dimensionless, in [0, 1]
      # Interpolation
      A_of_E = interp1d(E_bse, A_bse, kind="linear", bounds_error=False, fill_value=0.0)
      E_min, E_max = E_bse.min(), E_bse.max()
      mask = (E_sun >= E_min) & (E_sun <= E_max)
      E_int = E_sun[mask]
      A_int = A_of_E(E_int)
      I_sun_int = I_sun_E[mask]
      J_sc = get_short_circuit_current(E_int, A_int, I_sun_int)
      J0_rad = get_radiative_reverse_saturation_current(E_bse, A_bse, temperature, 100)
      J_0 = J0_rad / f_r
      V_oc_approx = kB_eV * temperature * np.log(J_sc / J_0 + 1.0)
      res = minimize_scalar(
        minus_power,
        bounds=(1e-6, V_oc_approx),
        method="bounded",
        args=(J_sc, J_0, temperature, kB_eV),
      )
      P_m = -res.fun
      V_mpp = res.x
      eta = 100 * P_m / P_in
      efficiencies[i] = eta
    ls = '-' if i_width == 1 else ':' if i_width == 2 else '--'
    color = plt.get_cmap('tab10')(i_phase)
    ax[i_phase].plot(thicknesses, efficiencies, ls, label=f"w = {width} eV", color=color)
    results.append(efficiencies)
  ax[i_phase].fill_between(thicknesses, results[0], results[-1], alpha=0.2, color=color)
  ax[i_phase].set_ylabel("Max. Efficiency [%]", fontsize=10)
  ax[i_phase].set_xlabel("Thickness [nm]", fontsize=10)
  ax[i_phase].tick_params(direction='in', axis='both', which='both', labelsize=8)
  ax[i_phase].set_xlim(1, 5e3)
  ax[i_phase].set_xscale('log')
  ax[i_phase].set_ylim(0, 40)
  ax[i_phase].legend(loc='upper left', title=phase, bbox_to_anchor=(0.02, 1.0), handlelength=1,
              handletextpad=0.5, ncol=1, fontsize=8)
