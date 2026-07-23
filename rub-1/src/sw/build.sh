file="${1-asm_functions.asm}"
stop_pc="${2-1}"

rm rom.mem
rm ../rtl/rom.mem

python assembler.py "${file}" rom.mem || exit 1
cd ..
cp -f ./sw/rom.mem ./rtl/rom.mem
make clean && make -j $(nproc) main_controller_app TEST=main_controller_app STOP_PC="${stop_pc}" INSTR_TRACE=1
cd sw
