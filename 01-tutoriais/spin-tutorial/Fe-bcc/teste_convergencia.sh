#!/bin/bash
# Teste de convergencia em ngridk para o Fe bcc.

K_MIN=4
K_MAX=16
K_STEP=2

ARQUIVO_DADOS="resultados_convergencia_k.dat"
echo "# ngridk | Total Energy (Ha) | Total Magnetic Moment (mu_B)" > $ARQUIVO_DADOS

for k in $(seq $K_MIN $K_STEP $K_MAX); do
    
    echo "ngridk: $k $k $k..."
    
    sed -i "s/ngridk=\"[^\"]*\"/ngridk=\"$k $k $k\"/g" input.xml
    
    exciting_smp > saida_terminal.log
    
    ENERGIA_TOTAL=$(grep -v '^$' TOTENERGY.OUT | tail -n 1 | awk '{print $1}')
    MOMENTO_TOTAL=$(grep "total moment " INFO.OUT | tail -n 1 | awk -F':' '{print $2}' | xargs)
    if [ -z "$MOMENTO_TOTAL" ]; then
        MOMENTO_TOTAL="0.0000"
    fi
    
    if [ -z "$ENERGIA_TOTAL" ]; then
        echo "ERRO: Falha ao extrair a energia da malha $k $k $k."
        exit 1
    fi

    echo "   $k      $ENERGIA_TOTAL     $MOMENTO_TOTAL" >> $ARQUIVO_DADOS
    
    rm -f *.OUT
done

echo "FIM."
rm -f saida_terminal.log
