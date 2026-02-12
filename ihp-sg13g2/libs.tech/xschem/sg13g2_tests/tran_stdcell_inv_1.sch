v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
F {}
E {}
B 2 270 -50 690 80 {flags=graph
y1=-0.00082
y2=1.3
ypos1=-1.7308809
ypos2=-0.43088093
divy=4
subdivy=1
unity=1
x1=0
x2=8e-06
divx=4
subdivx=1
xlabmag=1.0
ylabmag=1.0
node=vout
color=4
dataset=-1
unitx=1
logx=0
logy=0
digital=0}
B 2 270 90 690 220 {flags=graph
y1=0
y2=1.3
ypos1=-1.7308809
ypos2=-0.43088093
divy=4
subdivy=1
unity=1
x1=0
x2=8e-06
divx=4
subdivx=1
xlabmag=1.0
ylabmag=1.0
node=vin
color=4
dataset=-1
unitx=1
logx=0
logy=0
digital=0}
N -30 -40 40 -40 {lab=vout}
N -150 -40 -110 -40 {lab=vin}
N -150 -40 -150 -10 {lab=vin}
N -150 50 -150 80 {lab=GND}
N -180 -40 -150 -40 {lab=vin}
N 130 50 130 80 {lab=GND}
N 170 80 210 80 {lab=GND}
N 210 50 210 80 {lab=GND}
N 170 80 170 90 {lab=GND}
N 130 80 170 80 {lab=GND}
N 130 -40 130 -10 {lab=vdd}
N 210 -40 210 -10 {lab=vss}
C {sg13g2_stdcells/sg13g2_inv_1.sym} -70 -40 0 0 {name=x1 VDD=vdd VSS=vss prefix=sg13g2_ }
C {vsource.sym} 210 20 0 0 {name=V1 value=0 savecurrent=false}
C {vsource.sym} 130 20 0 0 {name=V2 value=1.2 savecurrent=false}
C {vsource.sym} -150 20 0 1 {name=V3 value="PULSE(0 1.2 0.5u 10n 10n 2u 4u 2)" savecurrent=false}
C {gnd.sym} 170 90 0 0 {name=l1 lab=GND}
C {gnd.sym} -150 80 0 0 {name=l3 lab=GND}
C {lab_wire.sym} 130 -40 0 0 {name=p1 sig_type=std_logic lab=vdd}
C {lab_wire.sym} 210 -40 0 1 {name=p2 sig_type=std_logic lab=vss}
C {lab_wire.sym} -180 -40 0 0 {name=p3 sig_type=std_logic lab=vin
}
C {lab_wire.sym} 40 -40 0 1 {name=p4 sig_type=std_logic lab=vout}
C {code_shown.sym} -330 160 0 0 {name=MODEL format="tcleval( @value )" only_toplevel=false value="
.include sg13g2_stdcell.spice
.lib cornerMOSlv.lib mos_tt
"}
C {code_shown.sym} -80 170 0 0 {name=NGSPICE only_toplevel=true value="
.control
tran 50n 8u
save all
write tran_stdcell_inv_1.raw
.endc
"}
C {launcher.sym} 280 250 0 0 {name=h5
descr="load waves (ctl + left click)" 
tclcommand="xschem raw_read $netlist_dir/tran_stdcell_inv_1.raw tran"
}
