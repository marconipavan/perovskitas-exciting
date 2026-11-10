#!/usr/bin/env bash
# Compila o exciting usando o container de ferramentas.
set -euo pipefail

IC="${IC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export container="$IC/exciting-toolchain.sif"
export exciting_dir="$IC/exciting"
export branch="sodium"
export build_dir="$IC/build-farm/build-$branch"
export install_dir="$IC/build-farm/install-$branch"

export cmake_custom="$exciting_dir/external/cmake-3.31.3-linux-x86_64/bin/cmake"
if [ ! -x "$cmake_custom" ]; then
    echo "AVISO: cmake embutido nao encontrado; usando o cmake do container."
    export cmake_custom="cmake"
fi

export FC=gfortran
export fftw3="-DFFTW3_ROOT=/usr/local/"

cd "$exciting_dir"

echo "==> 1/3  Configurando (cmake)"
apptainer exec "$container" $cmake_custom \
  -DMKL=OFF -DMPI=ON -DOMP=ON \
  -S "$exciting_dir" \
  -B "$build_dir" \
  -DCMAKE_INSTALL_PREFIX="$install_dir" \
  $fftw3 --fresh

echo "==> 2/3  Compilando (ajuste -j ao seu numero de nucleos)"
apptainer exec "$container" $cmake_custom --build "$build_dir" -j 4

echo "==> 3/3  Instalando"
apptainer exec "$container" $cmake_custom --install "$build_dir"

echo
echo "Pronto. Binario em: $install_dir/bin/exciting_mpismp"
