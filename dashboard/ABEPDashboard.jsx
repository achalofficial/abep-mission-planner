import React, { useState, useCallback, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine
} from "recharts";

// ─── NRLMSISE-00 pre-computed density table ────────────────────────────────
// Rows: [altitude_km, F10.7, Ap, rho_kg_m3]
// Grid: alt 180–250 (5 km steps) × F10.7 [70,100,140,180,220,250] × Ap [4,15,50,100,150,200,300]
const DENSITY_TABLE = [[180,70,4,3.571936e-10],[180,70,15,3.776358e-10],[180,70,50,4.043090e-10],[180,70,100,4.276561e-10],[180,70,150,4.508727e-10],[180,70,200,4.748600e-10],[180,70,300,5.253304e-10],[180,100,4,4.039094e-10],[180,100,15,4.255796e-10],[180,100,50,4.538909e-10],[180,100,100,4.785496e-10],[180,100,150,5.030435e-10],[180,100,200,5.283545e-10],[180,100,300,5.816351e-10],[180,140,4,4.641734e-10],[180,140,15,4.876923e-10],[180,140,50,5.184566e-10],[180,140,100,5.450953e-10],[180,140,150,5.715161e-10],[180,140,200,5.988174e-10],[180,140,300,6.562994e-10],[180,180,4,5.246251e-10],[180,180,15,5.501082e-10],[180,180,50,5.834769e-10],[180,180,100,6.122213e-10],[180,180,150,6.406916e-10],[180,180,200,6.701084e-10],[180,180,300,7.320501e-10],[180,220,4,5.861303e-10],[180,220,15,6.136337e-10],[180,220,50,6.496806e-10],[180,220,100,6.805895e-10],[180,220,150,7.111663e-10],[180,220,200,7.427565e-10],[180,220,300,8.092774e-10],[180,250,4,6.331164e-10],[180,250,15,6.621476e-10],[180,250,50,7.002191e-10],[180,250,100,7.327630e-10],[180,250,150,7.649299e-10],[180,250,200,7.981602e-10],[180,250,300,8.681340e-10],[185,70,4,2.919339e-10],[185,70,15,3.095293e-10],[185,70,50,3.325485e-10],[185,70,100,3.527332e-10],[185,70,150,3.728454e-10],[185,70,200,3.936676e-10],[185,70,300,4.376077e-10],[185,100,4,3.352196e-10],[185,100,15,3.540197e-10],[185,100,50,3.786381e-10],[185,100,100,4.001084e-10],[185,100,150,4.214710e-10],[185,100,200,4.435857e-10],[185,100,300,4.902589e-10],[185,140,4,3.909127e-10],[185,140,15,4.114953e-10],[185,140,50,4.384734e-10],[185,140,100,4.618558e-10],[185,140,150,4.850799e-10],[185,140,200,5.091152e-10],[185,140,300,5.598357e-10],[185,180,4,4.467707e-10],[185,180,15,4.692367e-10],[185,180,50,4.987085e-10],[185,180,100,5.241145e-10],[185,180,150,5.493096e-10],[185,180,200,5.753783e-10],[185,180,300,6.303819e-10],[185,220,4,5.036816e-10],[185,220,15,5.280827e-10],[185,220,50,5.601173e-10],[185,220,100,5.876018e-10],[185,220,150,6.148211e-10],[185,220,200,6.429780e-10],[185,220,300,7.023795e-10],[185,250,4,5.472342e-10],[185,250,15,5.730997e-10],[185,250,50,6.070737e-10],[185,250,100,6.361294e-10],[185,250,150,6.648781e-10],[185,250,200,6.946125e-10],[185,250,300,7.573346e-10],[190,70,4,2.402812e-10],[190,70,15,2.554893e-10],[190,70,50,2.754378e-10],[190,70,100,2.929608e-10],[190,70,150,3.104557e-10],[190,70,200,3.286049e-10],[190,70,300,3.670167e-10],[190,100,4,2.802681e-10],[190,100,15,2.966566e-10],[190,100,50,3.181658e-10],[190,100,100,3.369480e-10],[190,100,150,3.556668e-10],[190,100,200,3.750782e-10],[190,100,300,4.161501e-10],[190,140,4,3.316906e-10],[190,140,15,3.497955e-10],[190,140,50,3.735729e-10],[190,140,100,3.941995e-10],[190,140,150,4.147144e-10],[190,140,200,4.359776e-10],[190,140,300,4.809466e-10],[190,180,4,3.833089e-10],[190,180,15,4.032171e-10],[190,180,50,4.293795e-10],[190,180,100,4.519480e-10],[190,180,150,4.743556e-10],[190,180,200,4.975708e-10],[190,180,300,5.466492e-10],[190,220,4,4.359937e-10],[190,220,15,4.577522e-10],[190,220,50,4.863636e-10],[190,220,100,5.109243e-10],[190,220,150,5.352735e-10],[190,220,200,5.604918e-10],[190,220,300,6.137878e-10],[190,250,4,4.763868e-10],[190,250,15,4.995461e-10],[190,250,50,5.300119e-10],[190,250,100,5.560792e-10],[190,250,150,5.818962e-10],[190,250,200,6.086285e-10],[190,250,300,6.651117e-10],[195,70,4,1.990080e-10],[195,70,15,2.122010e-10],[195,70,50,2.295522e-10],[195,70,100,2.448206e-10],[195,70,150,2.600947e-10],[195,70,200,2.759723e-10],[195,70,300,3.096746e-10],[195,100,4,2.358551e-10],[195,100,15,2.502024e-10],[195,100,50,2.690749e-10],[195,100,100,2.855750e-10],[195,100,150,3.020458e-10],[195,100,200,3.191553e-10],[195,100,300,3.554466e-10],[195,140,4,2.833029e-10],[195,140,15,2.993013e-10],[195,140,50,3.203524e-10],[195,140,100,3.386296e-10],[195,140,150,3.568318e-10],[195,140,200,3.757253e-10],[195,140,300,4.157676e-10],[195,180,4,3.310149e-10],[195,180,15,3.487382e-10],[195,180,50,3.720690e-10],[195,180,100,3.922077e-10],[195,180,150,4.122255e-10],[195,180,200,4.329912e-10],[195,180,300,4.769738e-10],[195,220,4,3.798167e-10],[195,220,15,3.993074e-10],[195,220,50,4.249764e-10],[195,220,100,4.470224e-10],[195,220,150,4.689005e-10],[195,220,200,4.915856e-10],[195,220,300,5.396094e-10],[195,250,4,4.173055e-10],[195,250,15,4.381344e-10],[195,250,50,4.655746e-10],[195,250,100,4.890632e-10],[195,250,150,5.123480e-10],[195,250,200,5.364845e-10],[195,250,300,5.875639e-10],[200,70,4,1.657515e-10],[200,70,15,1.772338e-10],[200,70,50,1.923753e-10],[200,70,100,2.057229e-10],[200,70,150,2.191021e-10],[200,70,200,2.330381e-10],[200,70,300,2.627056e-10],[200,100,4,1.996340e-10],[200,100,15,2.122426e-10],[200,100,50,2.288646e-10],[200,100,100,2.434148e-10],[200,100,150,2.579622e-10],[200,100,200,2.730991e-10],[200,100,300,3.052849e-10],[200,140,4,2.433931e-10],[200,140,15,2.575881e-10],[200,140,50,2.763013e-10],[200,140,100,2.925621e-10],[200,140,150,3.087771e-10],[200,140,200,3.256315e-10],[200,140,300,3.614262e-10],[200,180,4,2.875094e-10],[200,180,15,3.033531e-10],[200,180,50,3.242442e-10],[200,180,100,3.422882e-10],[200,180,150,3.602434e-10],[200,180,200,3.788926e-10],[200,180,300,4.184638e-10],[200,220,4,3.327441e-10],[200,220,15,3.502750e-10],[200,220,50,3.733977e-10],[200,220,100,3.932663e-10],[200,220,150,4.130027e-10],[200,220,200,4.334899e-10],[200,220,300,4.769316e-10],[200,250,4,3.675634e-10],[200,250,15,3.863718e-10],[200,250,50,4.111852e-10],[200,250,100,4.324341e-10],[200,250,150,4.535175e-10],[200,250,200,4.753948e-10],[200,250,300,5.217643e-10],[205,70,4,1.387548e-10],[205,70,15,1.487774e-10],[205,70,50,1.620294e-10],[205,70,100,1.737324e-10],[205,70,150,1.854864e-10],[205,70,200,1.977544e-10],[205,70,300,2.239474e-10],[205,100,4,1.698567e-10],[205,100,15,1.809752e-10],[205,100,50,1.956651e-10],[205,100,100,2.085396e-10],[205,100,150,2.214318e-10],[205,100,200,2.348688e-10],[205,100,300,2.635091e-10],[205,140,4,2.101997e-10],[205,140,15,2.228410e-10],[205,140,50,2.395368e-10],[205,140,100,2.540564e-10],[205,140,150,2.685533e-10],[205,140,200,2.836427e-10],[205,140,300,3.157536e-10],[205,180,4,2.510068e-10],[205,180,15,2.652234e-10],[205,180,50,2.839992e-10],[205,180,100,3.002260e-10],[205,180,150,3.163903e-10],[205,180,200,3.331994e-10],[205,180,300,3.689292e-10],[205,220,4,2.929638e-10],[205,220,15,3.087905e-10],[205,220,50,3.296956e-10],[205,220,100,3.476674e-10],[205,220,150,3.655363e-10],[205,220,200,3.841050e-10],[205,220,300,4.235408e-10],[205,250,4,3.253281e-10],[205,250,15,3.423739e-10],[205,250,50,3.648927e-10],[205,250,100,3.841844e-10],[205,250,150,4.033427e-10],[205,250,200,4.232423e-10],[205,250,300,4.654825e-10],[210,70,4,1.166937e-10],[210,70,15,1.254653e-10],[210,70,50,1.370941e-10],[210,70,100,1.473823e-10],[210,70,150,1.577362e-10],[210,70,200,1.685647e-10],[210,70,300,1.917519e-10],[210,100,4,1.452014e-10],[210,100,15,1.550363e-10],[210,100,50,1.680585e-10],[210,100,100,1.794854e-10],[210,100,150,1.909459e-10],[210,100,200,2.029102e-10],[210,100,300,2.284725e-10],[210,140,4,1.823856e-10],[210,140,15,1.936809e-10],[210,140,50,2.086258e-10],[210,140,100,2.216335e-10],[210,140,150,2.346367e-10],[210,140,200,2.481898e-10],[210,140,300,2.770884e-10],[210,180,4,2.201472e-10],[210,180,15,2.329470e-10],[210,180,50,2.498782e-10],[210,180,100,2.645196e-10],[210,180,150,2.791198e-10],[210,180,200,2.943202e-10],[210,180,300,3.266861e-10],[210,220,4,2.590904e-10],[210,220,15,2.734264e-10],[210,220,50,2.923893e-10],[210,220,100,3.086991e-10],[210,220,150,3.249305e-10],[210,220,200,3.418150e-10],[210,220,300,3.777294e-10],[210,250,4,2.891953e-10],[210,250,15,3.046946e-10],[210,250,50,3.251974e-10],[210,250,100,3.427693e-10],[210,250,150,3.602344e-10],[210,250,200,3.783931e-10],[210,250,300,4.169934e-10],[215,70,4,9.855780e-11],[215,70,15,1.062527e-10],[215,70,50,1.164815e-10],[215,70,100,1.255479e-10],[215,70,150,1.346904e-10],[215,70,200,1.442715e-10],[215,70,300,1.648476e-10],[215,100,4,1.246558e-10],[215,100,15,1.333797e-10],[215,100,50,1.449556e-10],[215,100,100,1.551259e-10],[215,100,150,1.653420e-10],[215,100,200,1.760245e-10],[215,100,300,1.989024e-10],[215,140,4,1.589229e-10],[215,140,15,1.690459e-10],[215,140,50,1.824634e-10],[215,140,100,1.941513e-10],[215,140,150,2.058495e-10],[215,140,200,2.180586e-10],[215,140,300,2.441420e-10],[215,180,4,1.938810e-10],[215,180,15,2.054404e-10],[215,180,50,2.207545e-10],[215,180,100,2.340054e-10],[215,180,150,2.472326e-10],[215,180,200,2.610193e-10],[215,180,300,2.904244e-10],[215,220,4,2.300506e-10],[215,220,15,2.430758e-10],[215,220,50,2.603286e-10],[215,220,100,2.751745e-10],[215,220,150,2.899623e-10],[215,220,200,3.053609e-10],[215,220,300,3.381638e-10],[215,250,4,2.580739e-10],[215,250,15,2.722090e-10],[215,250,50,2.909315e-10],[215,250,100,3.069842e-10],[215,250,150,3.229526e-10],[215,250,200,3.395709e-10],[215,250,300,3.749463e-10],[220,70,4,8.356746e-11],[220,70,15,9.033262e-11],[220,70,50,9.934948e-11],[220,70,100,1.073567e-10],[220,70,150,1.154474e-10],[220,70,200,1.239435e-10],[220,70,300,1.422429e-10],[220,100,4,1.074357e-10],[220,100,15,1.151936e-10],[220,100,50,1.255097e-10],[220,100,100,1.345847e-10],[220,100,150,1.437145e-10],[220,100,200,1.532767e-10],[220,100,300,1.738031e-10],[220,140,4,1.390114e-10],[220,140,15,1.481085e-10],[220,140,50,1.601873e-10],[220,140,100,1.707179e-10],[220,140,150,1.812705e-10],[220,140,200,1.922983e-10],[220,140,300,2.159032e-10],[220,180,4,1.713877e-10],[220,180,15,1.818560e-10],[220,180,50,1.957453e-10],[220,180,100,2.077709e-10],[220,180,150,2.197870e-10],[220,180,200,2.323255e-10],[220,180,300,2.591123e-10],[220,220,4,2.050027e-10],[220,220,15,2.168695e-10],[220,220,50,2.326090e-10],[220,220,100,2.461594e-10],[220,220,150,2.596685e-10],[220,220,200,2.737498e-10],[220,220,300,3.037903e-10],[220,250,4,2.311062e-10],[220,250,15,2.440322e-10],[220,250,50,2.611747e-10],[220,250,100,2.758789e-10],[220,250,150,2.905177e-10],[220,250,200,3.057667e-10],[220,250,300,3.382715e-10],[225,70,4,7.111551e-11],[225,70,15,7.707510e-11],[225,70,50,8.503941e-11],[225,70,100,9.212546e-11],[225,70,150,9.929999e-11],[225,70,200,1.068492e-10],[225,70,300,1.231567e-10],[225,100,4,9.292679e-11],[225,100,15,9.984167e-11],[225,100,50,1.090562e-10],[225,100,100,1.171725e-10],[225,100,150,1.253505e-10],[225,100,200,1.339294e-10],[225,100,300,1.523881e-10],[225,140,4,1.220214e-10],[225,140,15,1.302169e-10],[225,140,50,1.411173e-10],[225,140,100,1.506286e-10],[225,140,150,1.601712e-10],[225,140,200,1.701564e-10],[225,140,300,1.915699e-10],[225,180,4,1.520191e-10],[225,180,15,1.615231e-10],[225,180,50,1.741518e-10],[225,180,100,1.850926e-10],[225,180,150,1.960357e-10],[225,180,200,2.074672e-10],[225,180,300,2.319286e-10],[225,220,4,1.832791e-10],[225,220,15,1.941174e-10],[225,220,50,2.085119e-10],[225,220,100,2.209104e-10],[225,220,150,2.332820e-10],[225,220,200,2.461901e-10],[225,220,300,2.737676e-10],[225,250,4,2.076101e-10],[225,250,15,2.194594e-10],[225,250,50,2.351934e-10],[225,250,100,2.486953e-10],[225,250,150,2.621480e-10],[225,250,200,2.761742e-10],[225,250,300,3.061125e-10],[230,70,4,6.072475e-11],[230,70,15,6.598439e-11],[230,70,50,7.303190e-11],[230,70,100,7.931449e-11],[230,70,150,8.568844e-11],[230,70,200,9.240886e-11],[230,70,300,1.069683e-10],[230,100,4,8.064362e-11],[230,100,15,8.682011e-11],[230,100,50,9.506788e-11],[230,100,100,1.023422e-10],[230,100,150,1.096830e-10],[230,100,200,1.173961e-10],[230,100,300,1.340300e-10],[230,140,4,1.074524e-10],[230,140,15,1.148524e-10],[230,140,50,1.247114e-10],[230,140,100,1.333215e-10],[230,140,150,1.419701e-10],[230,140,200,1.510314e-10],[230,140,300,1.704999e-10],[230,180,4,1.352577e-10],[230,180,15,1.439061e-10],[230,180,50,1.554146e-10],[230,180,100,1.653913e-10],[230,180,150,1.753800e-10],[230,180,200,1.858257e-10],[230,180,300,2.082134e-10],[230,220,4,1.643446e-10],[230,220,15,1.742662e-10],[230,220,50,1.874602e-10],[230,220,100,1.988305e-10],[230,220,150,2.101858e-10],[230,220,200,2.220449e-10],[230,220,300,2.474172e-10],[230,250,4,1.870377e-10],[230,250,15,1.979243e-10],[230,250,50,2.123975e-10],[230,250,100,2.248229e-10],[230,250,150,2.372129e-10],[230,250,200,2.501427e-10],[230,250,300,2.777772e-10],[235,70,4,5.201726e-11],[235,70,15,5.666712e-11],[235,70,50,6.291396e-11],[235,70,100,6.849383e-11],[235,70,150,7.416636e-11],[235,70,200,8.015930e-11],[235,70,300,9.318049e-11],[235,100,4,7.019901e-11],[235,100,15,7.572666e-11],[235,100,50,8.312329e-11],[235,100,100,8.965565e-11],[235,100,150,9.625788e-11],[235,100,200,1.032058e-10],[235,100,300,1.182241e-10],[235,140,4,9.490300e-11],[235,140,15,1.015986e-10],[235,140,50,1.105338e-10],[235,140,100,1.183442e-10],[235,140,150,1.261988e-10],[235,140,200,1.344386e-10],[235,140,300,1.521745e-10],[235,180,4,1.206866e-10],[235,180,15,1.285730e-10],[235,180,50,1.390824e-10],[235,180,100,1.481989e-10],[235,180,150,1.573353e-10],[235,180,200,1.669001e-10],[235,180,300,1.874316e-10],[235,220,4,1.477666e-10],[235,220,15,1.568678e-10],[235,220,50,1.689863e-10],[235,220,100,1.794351e-10],[235,220,150,1.898790e-10],[235,220,200,2.007967e-10],[235,220,300,2.241872e-10],[235,250,4,1.689445e-10],[235,250,15,1.789670e-10],[235,250,50,1.923073e-10],[235,250,100,2.037653e-10],[235,250,150,2.151996e-10],[235,250,200,2.271426e-10],[235,250,300,2.527011e-10],[240,70,4,4.469155e-11],[240,70,15,4.880893e-11],[240,70,50,5.435482e-11],[240,70,100,5.931858e-11],[240,70,150,6.437502e-11],[240,70,200,6.972782e-11],[240,70,300,8.139184e-11],[240,100,4,6.128177e-11],[240,100,15,6.623760e-11],[240,100,50,7.288264e-11],[240,100,100,7.875925e-11],[240,100,150,8.470784e-11],[240,100,200,9.097771e-11],[240,100,300,1.045613e-10],[240,140,4,8.404851e-11],[240,140,15,9.011817e-11],[240,140,50,9.823145e-11],[240,140,100,1.053298e-10],[240,140,150,1.124768e-10],[240,140,200,1.199835e-10],[240,140,300,1.361711e-10],[240,180,4,1.079671e-10],[240,180,15,1.151723e-10],[240,180,50,1.247875e-10],[240,180,100,1.331340e-10],[240,180,150,1.415068e-10],[240,180,200,1.502814e-10],[240,180,300,1.691460e-10],[240,220,4,1.331921e-10],[240,220,15,1.415566e-10],[240,220,50,1.527080e-10],[240,220,100,1.623281e-10],[240,220,150,1.719519e-10],[240,220,200,1.820216e-10],[240,220,300,2.036249e-10],[240,250,4,1.529671e-10],[240,250,15,1.622113e-10],[240,250,50,1.745298e-10],[240,250,100,1.851153e-10],[240,250,150,1.956872e-10],[240,250,200,2.067389e-10],[240,250,300,2.304202e-10],[245,70,4,3.850559e-11],[245,70,15,4.215696e-11],[245,70,50,4.708786e-11],[245,70,100,5.151022e-11],[245,70,150,5.602430e-11],[245,70,200,6.081251e-11],[245,70,300,7.127636e-11],[245,100,4,5.364002e-11],[245,100,15,5.809053e-11],[245,100,50,6.407009e-11],[245,100,100,6.936556e-11],[245,100,150,7.473410e-11],[245,100,200,8.040142e-11],[245,100,300,9.270737e-11],[245,140,4,7.462429e-11],[245,140,15,8.013615e-11],[245,140,50,8.751576e-11],[245,140,100,9.397827e-11],[245,140,150,1.004927e-10],[245,140,200,1.073435e-10],[245,140,300,1.221431e-10],[245,180,4,9.682148e-11],[245,180,15,1.034160e-10],[245,180,50,1.122283e-10],[245,180,100,1.198832e-10],[245,180,150,1.275697e-10],[245,180,200,1.356334e-10],[245,180,300,1.529962e-10],[245,220,4,1.203307e-10],[245,220,15,1.280314e-10],[245,220,50,1.383105e-10],[245,220,100,1.471830e-10],[245,220,150,1.560663e-10],[245,220,200,1.653699e-10],[245,220,300,1.853564e-10],[245,250,4,1.388057e-10],[245,250,15,1.473465e-10],[245,250,50,1.587406e-10],[245,250,100,1.685366e-10],[245,250,150,1.783276e-10],[245,250,200,1.885718e-10],[245,250,300,2.105503e-10],[250,70,4,3.326391e-11],[250,70,15,3.650663e-11],[250,70,50,4.089685e-11],[250,70,100,4.484247e-11],[250,70,150,4.887809e-11],[250,70,200,5.316729e-11],[250,70,300,6.256752e-11],[250,100,4,4.706848e-11],[250,100,15,5.107134e-11],[250,100,50,5.646021e-11],[250,100,100,6.123936e-11],[250,100,150,6.609187e-11],[250,100,200,7.122237e-11],[250,100,300,8.238771e-11],[250,140,4,6.641315e-11],[250,140,15,7.142652e-11],[250,140,50,7.814943e-11],[250,140,100,8.404253e-11],[250,140,150,8.998987e-11],[250,140,200,9.625198e-11],[250,140,300,1.098041e-10],[250,180,4,8.702091e-11],[250,180,15,9.306621e-11],[250,180,50,1.011556e-10],[250,180,100,1.081876e-10],[250,180,150,1.152553e-10],[250,180,200,1.226776e-10],[250,180,300,1.386834e-10],[250,220,4,1.089419e-10],[250,220,15,1.160428e-10],[250,220,50,1.255326e-10],[250,220,100,1.337286e-10],[250,220,150,1.419414e-10],[250,220,200,1.505505e-10],[250,220,300,1.690700e-10],[250,250,4,1.262113e-10],[250,250,15,1.341144e-10],[250,250,50,1.446697e-10],[250,250,100,1.537492e-10],[250,250,150,1.628310e-10],[250,250,200,1.723413e-10],[250,250,300,1.927704e-10]];

// ─── Build lookup: rhoLookup[alt][f107][ap] = rho ─────────────────────────
const rhoLookup = {};
for (const [alt, f107, ap, rho] of DENSITY_TABLE) {
  if (!rhoLookup[alt]) rhoLookup[alt] = {};
  if (!rhoLookup[alt][f107]) rhoLookup[alt][f107] = {};
  rhoLookup[alt][f107][ap] = rho;
}

// ─── Physics engine ────────────────────────────────────────────────────────
const GM = 3.986004418e14;
const R_EARTH = 6_371_000;
const G0 = 9.80665;
const SOLAR_K = 1361;

function orbitalVelocity(altKm) {
  return Math.sqrt(GM / (R_EARTH + altKm * 1000));
}

function computePhysics(rho, altKm, params) {
  const { Cd, frontalArea, intakeArea, intakeEff, isp, tpRatio, panelArea, panelEff, eclipse, housekeeping, ionEff } = params;
  const v = orbitalVelocity(altKm);
  const Fdrag = 0.5 * rho * v * v * Cd * frontalArea;
  const mdot = rho * v * intakeArea * intakeEff;
  const vExh = isp * G0;
  const Fprop = mdot * vExh * ionEff;
  const Psolar = panelArea * SOLAR_K * panelEff * (1 - eclipse);
  const Pavail = Math.max(Psolar - housekeeping, 0);
  const Fpwr = Pavail * tpRatio * 1e-6;
  const Feff = Math.min(Fprop, Fpwr);
  const ratio = Fdrag > 0 ? Feff / Fdrag : 99;
  return {
    ratio,
    Fdrag_mN: Fdrag * 1000,
    Feff_mN: Feff * 1000,
    Fprop_mN: Fprop * 1000,
    Fpwr_mN: Fpwr * 1000,
    Pavail_W: Pavail,
    limiter: Fprop < Fpwr ? "PROP" : "PWR",
    rho,
  };
}

function getRho(altKm, f107, apKey) {
  const altGrid = [180,185,190,195,200,205,210,215,220,225,230,235,240,245,250];
  const f107Grid = [70,100,140,180,220,250];
  const apGrid = [4,15,50,100,150,200,300];
  const nearAlt = altGrid.reduce((a,b) => Math.abs(b-altKm)<Math.abs(a-altKm)?b:a);
  const nearF107 = f107Grid.reduce((a,b) => Math.abs(b-f107)<Math.abs(a-f107)?b:a);
  const nearAp = apGrid.reduce((a,b) => Math.abs(b-apKey)<Math.abs(a-apKey)?b:a);
  return rhoLookup[nearAlt]?.[nearF107]?.[nearAp] ?? 2e-10;
}

// ─── Status classification ──────────────────────────────────────────────────
function classify(ratio) {
  if (ratio > 1.5) return "SAFE";
  if (ratio >= 1.2) return "ADEQUATE";
  if (ratio >= 1.0) return "MARGINAL";
  return "FAILURE";
}

const STATUS_COLOR = {
  SAFE:     "#22c55e",
  ADEQUATE: "#84cc16",
  MARGINAL: "#eab308",
  FAILURE:  "#ef4444",
};

function ratioColor(ratio) {
  if (ratio >= 1.5) return "#22c55e";
  if (ratio >= 1.2) return "#84cc16";
  if (ratio >= 1.0) return "#eab308";
  if (ratio >= 0.6) return "#f97316";
  return "#ef4444";
}

// ─── Analysis engine ────────────────────────────────────────────────────────
const F107_VALS = [70, 100, 140, 180, 220, 250];
const ALT_VALS  = [180,185,190,195,200,205,210,215,220,225,230,235,240,245,250];
const AP_SWEEP  = [4, 15, 50, 100, 150, 200, 300];

function runAnalysis(altTarget, isp, intakeEff, panelArea) {
  const params = {
    Cd: 2.2, frontalArea: 1.2,
    intakeArea: 1.0, intakeEff,
    isp, tpRatio: 25,
    panelArea, panelEff: 0.30,
    eclipse: 0.35, housekeeping: 50,
    ionEff: 0.70,
  };

  // Heatmap: altitude × F10.7, averaged over all Ap values (quiet+storm mix)
  const heatmap = [];
  for (const alt of ALT_VALS) {
    for (const f107 of F107_VALS) {
      // Compute ratio for quiet (Ap=4) and storm (Ap=150) conditions
      const rhoQuiet = getRho(alt, f107, 4);
      const rhoStorm = getRho(alt, f107, 150);
      const quiet = computePhysics(rhoQuiet, alt, params);
      const storm = computePhysics(rhoStorm, alt, params);
      heatmap.push({
        alt, f107,
        ratioQuiet: quiet.ratio,
        ratioStorm: storm.ratio,
        ratio: quiet.ratio, // displayed by default
        status: classify(quiet.ratio),
        limiter: quiet.limiter,
      });
    }
  }

  // Sweep all conditions for summary stats
  let total = 0, failures = 0, marginals = 0;
  const altFailureRate = {};
  for (const alt of ALT_VALS) {
    let altFail = 0, altTotal = 0;
    for (const f107 of F107_VALS) {
      for (const ap of AP_SWEEP) {
        const rho = getRho(alt, f107, ap);
        const { ratio } = computePhysics(rho, alt, params);
        total++;
        altTotal++;
        if (ratio < 1.0) { failures++; altFail++; }
        else if (ratio < 1.2) marginals++;
      }
    }
    altFailureRate[alt] = altFail / altTotal;
  }
  const failureRate = failures / total;

  // Recommended altitude: lowest alt with <30% failure rate
  const sortedAlts = [...ALT_VALS].sort((a,b)=>a-b);
  let recommendedAlt = sortedAlts[sortedAlts.length - 1];
  for (const alt of sortedAlts) {
    if (altFailureRate[alt] < 0.30) { recommendedAlt = alt; break; }
  }

  // Boundary zone
  let boundaryLow = null, boundaryHigh = null;
  for (const alt of sortedAlts) {
    if (altFailureRate[alt] >= 0.80 && (boundaryLow === null || alt > boundaryLow)) boundaryLow = alt;
    if (altFailureRate[alt] <= 0.20 && (boundaryHigh === null || alt < boundaryHigh)) boundaryHigh = alt;
  }

  // Crossover density at target altitude
  const v = orbitalVelocity(altTarget);
  const vExh = isp * G0;
  const Psolar = panelArea * SOLAR_K * 0.30 * (1 - 0.35);
  const Pavail = Math.max(Psolar - 50, 0);
  const rhoCrossover = (Pavail * 25e-6) / (v * 1.0 * intakeEff * vExh * 0.70);
  const propRatioConst = (1.0 * intakeEff * vExh * 0.70) / (0.5 * v * 2.2 * 1.2);

  // Target altitude stats
  const targetQuietRho = getRho(altTarget, 140, 4);
  const targetStormRho = getRho(altTarget, 250, 300);
  const targetQuiet = computePhysics(targetQuietRho, altTarget, params);
  const targetStorm = computePhysics(targetStormRho, altTarget, params);

  // Storm recovery chart data
  const stormScenarios = [
    { name: "Minor\nKp5",    label: "Minor (Kp5)",    ap: 50,  durationH: 6,  f107: 140 },
    { name: "Moderate\nKp6", label: "Moderate (Kp6)", ap: 100, durationH: 12, f107: 140 },
    { name: "Strong\nKp7",   label: "Strong (Kp7)",   ap: 150, durationH: 24, f107: 200 },
    { name: "Severe\nKp8",   label: "Severe (Kp8)",   ap: 200, durationH: 24, f107: 250 },
    { name: "Extreme\nKp9",  label: "Extreme (Kp9)",  ap: 300, durationH: 48, f107: 250 },
  ];

  const stormData = stormScenarios.map(s => {
    const rho = getRho(altTarget, s.f107, s.ap);
    const ph = computePhysics(rho, altTarget, params);
    // Altitude loss: simplified integration
    const a = R_EARTH + altTarget * 1000;
    const nOrb = Math.sqrt(GM / (a*a*a));
    const Fnet = Math.max(ph.Fdrag_mN - ph.Feff_mN, 0) / 1000; // N
    const dhdt = -2 * Fnet / (200 * nOrb); // m/s
    const altLoss = Math.max(dhdt * s.durationH * 3600 / 1000, 0); // km (positive = loss)
    return {
      name: s.label,
      altLoss: parseFloat(altLoss.toFixed(2)),
      ratio: parseFloat(ph.ratio.toFixed(3)),
      status: classify(ph.ratio),
      survived: altLoss < altTarget - 150,
    };
  });

  // Key findings
  const findings = [];
  findings.push(`Propellant-limited T/D ratio: ${propRatioConst.toFixed(3)} (density-independent)`);
  findings.push(`Crossover density at ${altTarget} km: ${rhoCrossover.toExponential(2)} kg/m³`);
  if (targetQuiet.ratio >= 1.0 && targetStorm.ratio < 1.0) {
    findings.push(`Quiet conditions: ${classify(targetQuiet.ratio)} (ratio ${targetQuiet.ratio.toFixed(2)})`);
    findings.push(`Solar max storm: FAILURE (ratio ${targetStorm.ratio.toFixed(2)}) — power-limited`);
  } else if (targetQuiet.ratio < 1.0) {
    findings.push(`Even quiet conditions fail at ${altTarget} km — altitude too low`);
    findings.push(`Try altitude ≥ ${recommendedAlt} km for viable operation`);
  } else {
    findings.push(`Target altitude appears viable in most conditions`);
    findings.push(`Solar max storm ratio: ${targetStorm.ratio.toFixed(2)} (${classify(targetStorm.ratio)})`);
  }
  if (boundaryLow && boundaryHigh) {
    findings.push(`Failure boundary: ${boundaryLow}–${boundaryHigh} km transition zone`);
  }

  const verdict =
    failureRate < 0.20 ? "FEASIBLE" :
    failureRate < 0.50 ? "FEASIBLE WITH CAVEATS" :
    "NOT FEASIBLE";

  return { heatmap, failureRate, verdict, recommendedAlt, findings, stormData, boundaryLow, boundaryHigh, altFailureRate };
}

// ─── Subcomponents ──────────────────────────────────────────────────────────

function SliderRow({ label, unit, value, min, max, step, onChange, format }) {
  return (
    <div className="mb-4">
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-xs font-medium text-slate-300 uppercase tracking-wider">{label}</span>
        <span className="text-sm font-mono font-bold text-cyan-400">
          {format ? format(value) : value}{unit}
        </span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
        style={{
          background: `linear-gradient(to right, #06b6d4 0%, #06b6d4 ${((value-min)/(max-min))*100}%, #334155 ${((value-min)/(max-min))*100}%, #334155 100%)`
        }}
      />
      <div className="flex justify-between text-xs text-slate-500 mt-0.5">
        <span>{min}{unit}</span><span>{max}{unit}</span>
      </div>
    </div>
  );
}

function HeatmapCell({ ratio, isTarget }) {
  const bg = ratioColor(ratio);
  const text = ratio >= 10 ? "—" : ratio.toFixed(2);
  return (
    <div
      className={`flex items-center justify-center text-xs font-mono font-bold transition-all
        ${isTarget ? "ring-2 ring-white ring-offset-1 ring-offset-slate-900 z-10 relative" : ""}`}
      style={{ backgroundColor: bg + "cc", color: "#fff", fontSize: "0.65rem", height: "100%", width: "100%" }}
      title={`Ratio: ${ratio.toFixed(3)}`}
    >
      {text}
    </div>
  );
}

function VerdictBadge({ verdict }) {
  const color =
    verdict === "FEASIBLE" ? "bg-green-500/20 text-green-400 border-green-500/40" :
    verdict === "FEASIBLE WITH CAVEATS" ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/40" :
    "bg-red-500/20 text-red-400 border-red-500/40";
  return (
    <div className={`inline-flex items-center px-3 py-1.5 rounded-md border text-xs font-bold tracking-wider uppercase ${color}`}>
      {verdict}
    </div>
  );
}

const CustomStormTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 text-xs shadow-xl">
      <p className="font-bold text-white mb-1">{label}</p>
      <p style={{ color: d?.survived ? "#22c55e" : "#ef4444" }}>
        {d?.survived ? "Survivable" : "Deorbit risk"}
      </p>
      <p className="text-slate-300">Alt loss: <span className="text-cyan-400 font-mono">{payload[0].value.toFixed(2)} km</span></p>
      <p className="text-slate-300">T/D ratio: <span className="font-mono" style={{color: ratioColor(d?.ratio)}}>{d?.ratio?.toFixed(3)}</span></p>
    </div>
  );
};

// ─── Main Dashboard ─────────────────────────────────────────────────────────
export default function ABEPDashboard() {
  const [altitude,    setAltitude]    = useState(210);
  const [isp,         setIsp]         = useState(5000);
  const [intakeEff,   setIntakeEff]   = useState(0.40);
  const [panelArea,   setPanelArea]   = useState(4.0);
  const [results,     setResults]     = useState(() => runAnalysis(210, 5000, 0.40, 4.0));
  const [running,     setRunning]     = useState(false);
  const [heatmapMode, setHeatmapMode] = useState("quiet"); // "quiet" | "storm"

  const handleRun = useCallback(() => {
    setRunning(true);
    setTimeout(() => {
      setResults(runAnalysis(altitude, isp, intakeEff, panelArea));
      setRunning(false);
    }, 30);
  }, [altitude, isp, intakeEff, panelArea]);

  const { heatmap, failureRate, verdict, recommendedAlt, findings, stormData, boundaryLow, boundaryHigh } = results;

  // Build heatmap grid: rows=alt (desc), cols=F10.7
  const heatRows = useMemo(() => {
    const byAlt = {};
    for (const cell of heatmap) {
      if (!byAlt[cell.alt]) byAlt[cell.alt] = {};
      byAlt[cell.alt][cell.f107] = cell;
    }
    return [...ALT_VALS].sort((a,b)=>b-a).map(alt => ({
      alt,
      cells: F107_VALS.map(f107 => byAlt[alt]?.[f107]),
    }));
  }, [heatmap]);

  const stormBarData = stormData.map(d => ({
    ...d,
    fill: d.survived ? "#06b6d4" : "#ef4444",
  }));

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans" style={{fontFamily: "'Inter', 'system-ui', sans-serif"}}>
      {/* ── Header ── */}
      <header className="border-b border-slate-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center">
            <svg viewBox="0 0 24 24" className="w-4 h-4 text-cyan-400 fill-current">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-wide">ABEP Mission Planner</h1>
            <p className="text-xs text-slate-500">Very Low Earth Orbit · Air-Breathing Electric Propulsion</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
            NRLMSISE-00 Model
          </span>
          <span>630 pre-computed density points</span>
        </div>
      </header>

      {/* ── Main layout ── */}
      <div className="flex gap-0 h-[calc(100vh-52px-180px)] min-h-0">

        {/* ── Left: Controls ── */}
        <aside className="w-64 flex-shrink-0 border-r border-slate-800 p-5 flex flex-col overflow-y-auto">
          <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-5">
            Mission Parameters
          </h2>

          <SliderRow label="Target Altitude" unit=" km" value={altitude}
            min={180} max={250} step={5} onChange={setAltitude} />
          <SliderRow label="Thruster Isp" unit=" s" value={isp}
            min={3000} max={6000} step={100} onChange={setIsp} />
          <SliderRow label="Intake Efficiency" unit="" value={intakeEff}
            min={0.30} max={0.50} step={0.01} onChange={setIntakeEff}
            format={v => (v*100).toFixed(0) + "%"} />
          <SliderRow label="Solar Panel Area" unit=" m²" value={panelArea}
            min={3.0} max={6.0} step={0.5} onChange={setPanelArea} />

          <div className="mt-2 mb-5 pt-4 border-t border-slate-800">
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Fixed Parameters</h3>
            {[
              ["Mass", "200 kg"],
              ["Frontal Area", "1.2 m²"],
              ["Cd (free mol.)", "2.2"],
              ["Intake Area", "1.0 m²"],
              ["T/P Ratio", "25 mN/kW"],
              ["Panel Efficiency", "30%"],
              ["Eclipse Fraction", "35%"],
            ].map(([k,v]) => (
              <div key={k} className="flex justify-between text-xs py-0.5">
                <span className="text-slate-500">{k}</span>
                <span className="text-slate-300 font-mono">{v}</span>
              </div>
            ))}
          </div>

          <button
            onClick={handleRun}
            disabled={running}
            className={`mt-auto w-full py-2.5 rounded-lg text-sm font-bold tracking-wide transition-all
              ${running
                ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                : "bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-lg shadow-cyan-500/20 cursor-pointer"
              }`}
          >
            {running ? "Computing..." : "▶  Run Analysis"}
          </button>
        </aside>

        {/* ── Center: Heatmap ── */}
        <main className="flex-1 min-w-0 p-5 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-bold text-white">Thrust/Drag Ratio Map</h2>
              <p className="text-xs text-slate-500 mt-0.5">Altitude × Solar Flux — NRLMSISE-00 atmosphere</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Condition:</span>
              <div className="flex rounded-md overflow-hidden border border-slate-700">
                {["quiet","storm"].map(mode => (
                  <button key={mode}
                    onClick={() => setHeatmapMode(mode)}
                    className={`px-3 py-1 text-xs font-medium transition-colors
                      ${heatmapMode === mode ? "bg-cyan-500/20 text-cyan-400" : "text-slate-400 hover:text-slate-200"}`}
                  >
                    {mode === "quiet" ? "Quiet (Ap=4)" : "Storm (Ap=150)"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 mb-3 text-xs">
            {[["SAFE >1.5","#22c55e"],["ADEQUATE 1.2–1.5","#84cc16"],["MARGINAL 1.0–1.2","#eab308"],["FAILURE <1.0","#ef4444"]].map(([l,c])=>(
              <div key={l} className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm" style={{backgroundColor: c}}/>
                <span className="text-slate-400">{l}</span>
              </div>
            ))}
            <div className="ml-3 flex items-center gap-1.5">
              <div className="w-4 h-4 rounded-sm ring-2 ring-white ring-offset-1 ring-offset-slate-950 bg-transparent"/>
              <span className="text-slate-400">Target altitude</span>
            </div>
          </div>

          {/* Heatmap grid */}
          <div className="flex-1 min-h-0 overflow-hidden">
            <div className="h-full flex flex-col">
              {/* F10.7 header */}
              <div className="flex mb-1 pl-14">
                {F107_VALS.map(f => (
                  <div key={f} className="flex-1 text-center text-xs text-slate-400 font-mono">{f}</div>
                ))}
              </div>
              <div className="text-xs text-slate-500 text-center mb-0.5">F10.7 Solar Flux (SFU) →</div>

              {/* Rows */}
              <div className="flex-1 min-h-0 flex flex-col gap-px">
                {heatRows.map(({ alt, cells }) => (
                  <div key={alt} className="flex items-center gap-px flex-1 min-h-0">
                    <div className={`w-12 text-right pr-2 text-xs font-mono flex-shrink-0
                      ${alt === altitude ? "text-cyan-400 font-bold" : "text-slate-500"}`}>
                      {alt}
                    </div>
                    <div className="text-xs text-slate-600 w-1 flex-shrink-0">—</div>
                    {cells.map((cell, i) => cell ? (
                      <div key={i} className="flex-1 min-h-0 h-full">
                        <HeatmapCell
                          ratio={heatmapMode === "quiet" ? cell.ratioQuiet : cell.ratioStorm}
                          isTarget={alt === altitude}
                        />
                      </div>
                    ) : <div key={i} className="flex-1"/>)}
                  </div>
                ))}
              </div>
              <div className="text-xs text-slate-500 text-center mt-1">↑ Altitude (km)</div>
            </div>
          </div>
        </main>

        {/* ── Right: Summary ── */}
        <aside className="w-72 flex-shrink-0 border-l border-slate-800 p-5 flex flex-col overflow-y-auto">
          <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">
            Mission Summary
          </h2>

          <VerdictBadge verdict={verdict} />

          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="bg-slate-900 rounded-lg p-3 border border-slate-800">
              <div className="text-xs text-slate-500 mb-1">Failure Rate</div>
              <div className={`text-xl font-bold font-mono ${
                failureRate < 0.2 ? "text-green-400" :
                failureRate < 0.5 ? "text-yellow-400" : "text-red-400"
              }`}>
                {(failureRate * 100).toFixed(1)}%
              </div>
              <div className="text-xs text-slate-500 mt-0.5">of all conditions</div>
            </div>
            <div className="bg-slate-900 rounded-lg p-3 border border-slate-800">
              <div className="text-xs text-slate-500 mb-1">Safe Altitude</div>
              <div className="text-xl font-bold font-mono text-cyan-400">{recommendedAlt}</div>
              <div className="text-xs text-slate-500 mt-0.5">km minimum</div>
            </div>
          </div>

          {boundaryLow && boundaryHigh && (
            <div className="mt-3 bg-slate-900 rounded-lg p-3 border border-yellow-500/20">
              <div className="text-xs text-yellow-400 font-medium mb-1">Boundary Zone</div>
              <div className="text-sm font-mono text-white">{boundaryLow} – {boundaryHigh} km</div>
              <div className="text-xs text-slate-500 mt-0.5">failure transition region</div>
            </div>
          )}

          <div className="mt-4">
            <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Key Findings</div>
            <div className="space-y-2">
              {findings.map((f, i) => (
                <div key={i} className="flex gap-2 text-xs">
                  <span className="text-cyan-500 flex-shrink-0 mt-0.5">◆</span>
                  <span className="text-slate-300 leading-relaxed">{f}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Per-altitude failure rate bar */}
          <div className="mt-4">
            <div className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
              Failure Rate by Altitude
            </div>
            <div className="space-y-1">
              {[...ALT_VALS].sort((a,b)=>b-a).map(alt => {
                const fr = results.altFailureRate?.[alt] ?? 0;
                return (
                  <div key={alt} className={`flex items-center gap-2 text-xs ${alt===altitude?"opacity-100":"opacity-70"}`}>
                    <span className={`w-7 text-right font-mono flex-shrink-0 ${alt===altitude?"text-cyan-400 font-bold":"text-slate-500"}`}>{alt}</span>
                    <div className="flex-1 h-3 bg-slate-800 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-500"
                        style={{
                          width: `${fr*100}%`,
                          backgroundColor: fr<0.2?"#22c55e":fr<0.5?"#eab308":"#ef4444"
                        }}/>
                    </div>
                    <span className={`w-8 text-right font-mono flex-shrink-0 ${fr<0.2?"text-green-400":fr<0.5?"text-yellow-400":"text-red-400"}`}>
                      {(fr*100).toFixed(0)}%
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </aside>
      </div>

      {/* ── Bottom: Storm Recovery ── */}
      <div className="border-t border-slate-800 px-6 py-4" style={{height: 180}}>
        <div className="flex items-center justify-between mb-2">
          <div>
            <h2 className="text-sm font-bold text-white">Storm Recovery Analysis</h2>
            <p className="text-xs text-slate-500">Altitude loss from {altitude} km per storm severity (1-step integration)</p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-cyan-500"/><span className="text-slate-400">Survivable</span></div>
            <div className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm bg-red-500"/><span className="text-slate-400">Deorbit risk</span></div>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={110}>
          <BarChart data={stormBarData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false}/>
            <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false}/>
            <YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false}
              label={{ value: "Alt loss (km)", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 10, dy: 40 }}/>
            <Tooltip content={<CustomStormTooltip/>} cursor={{ fill: "#ffffff0a" }}/>
            <ReferenceLine y={0} stroke="#334155" strokeWidth={1}/>
            <Bar dataKey="altLoss" radius={[4,4,0,0]} maxBarSize={60}>
              {stormBarData.map((entry, index) => (
                <Cell key={index} fill={entry.survived ? "#06b6d4" : "#ef4444"}
                  fillOpacity={entry.survived ? 0.85 : 0.9}/>
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
