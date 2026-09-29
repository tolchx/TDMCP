uint flatten3(ivec3 c, uint R){
    return uint(c.x) + R * (uint(c.y) + R * uint(c.z));
}

void main(){
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;

    // --- lecture
    vec3 u    = TDIn_U();          // vitesse actuelle
    vec3 Fext = TDIn_ForcesIn();   // forces externes
    float T   = TDIn_Temp();       // température

    // --- métriques
    uint R = max(SimRes, 1u);
    vec3 size  = vec3(SimSizex, SimSizey, SimSizez);
    vec3 h     = size / float(R);
    vec3 inv2h = 0.5 / h;

    // --- indices & voisins
    uint i =  id              % R;
    uint j = (id / R)         % R;
    uint k =  id / (R*R);
    ivec3 I  = ivec3(int(i), int(j), int(k));
    ivec3 lo = ivec3(0), hi = ivec3(int(R)-1);

    ivec3 L = clamp(I + ivec3(-1, 0, 0), lo, hi);
    ivec3 Rr= clamp(I + ivec3( 1, 0, 0), lo, hi);
    ivec3 D = clamp(I + ivec3( 0,-1, 0), lo, hi);
    ivec3 Uu= clamp(I + ivec3( 0, 1, 0), lo, hi);
    ivec3 B = clamp(I + ivec3( 0, 0,-1), lo, hi);
    ivec3 F = clamp(I + ivec3( 0, 0, 1), lo, hi);

    vec3 uL = TDIn_U(0, flatten3(L,  R));
    vec3 uR = TDIn_U(0, flatten3(Rr, R));
    vec3 uD = TDIn_U(0, flatten3(D,  R));
    vec3 uU = TDIn_U(0, flatten3(Uu, R));
    vec3 uB = TDIn_U(0, flatten3(B,  R));
    vec3 uF = TDIn_U(0, flatten3(F,  R));

    // --- vorticité locale ω = ∇ × u (différences centrées)
    float dw_dy = (uU.z - uD.z) * inv2h.y;
    float dv_dz = (uF.y - uB.y) * inv2h.z;
    float du_dz = (uF.x - uB.x) * inv2h.z;
    float dw_dx = (uR.z - uL.z) * inv2h.x;
    float dv_dx = (uR.y - uL.y) * inv2h.x;
    float du_dy = (uU.x - uD.x) * inv2h.y;

    vec3 omega = vec3( dw_dy - dv_dz,
                       du_dz - dw_dx,
                       dv_dx - du_dy );

    // --- |ω| aux 6 voisins (approx locale) pour ∇|ω|
    ivec3 LL = clamp(L + ivec3(-1,0,0), lo, hi);
    vec3 uLL = TDIn_U(0, flatten3(LL, R));
    float wL_z_y = (TDIn_U(0, flatten3(clamp(L + ivec3(0,1,0),lo,hi),R)).z
                   -TDIn_U(0, flatten3(clamp(L + ivec3(0,-1,0),lo,hi),R)).z) * inv2h.y;
    float vL_y_z = (TDIn_U(0, flatten3(clamp(L + ivec3(0,0,1),lo,hi),R)).y
                   -TDIn_U(0, flatten3(clamp(L + ivec3(0,0,-1),lo,hi),R)).y) * inv2h.z;
    float uL_x_z = (TDIn_U(0, flatten3(clamp(L + ivec3(0,0,1),lo,hi),R)).x
                   -TDIn_U(0, flatten3(clamp(L + ivec3(0,0,-1),lo,hi),R)).x) * inv2h.z;
    float wL_x_x = (uL.z - uLL.z) * inv2h.x;
    float vL_x_x = (uL.y - uLL.y) * inv2h.x;
    float uL_x_y = (TDIn_U(0, flatten3(clamp(L + ivec3(0,1,0),lo,hi),R)).x
                   -TDIn_U(0, flatten3(clamp(L + ivec3(0,-1,0),lo,hi),R)).x) * inv2h.y;
    vec3 omegaL = vec3(wL_z_y - vL_y_z, uL_x_z - wL_x_x, vL_x_x - uL_x_y);

    ivec3 RR = clamp(Rr + ivec3(1,0,0), lo, hi);
    vec3 uRR = TDIn_U(0, flatten3(RR, R));
    float wR_z_y = (TDIn_U(0, flatten3(clamp(Rr + ivec3(0,1,0),lo,hi),R)).z
                   -TDIn_U(0, flatten3(clamp(Rr + ivec3(0,-1,0),lo,hi),R)).z) * inv2h.y;
    float vR_y_z = (TDIn_U(0, flatten3(clamp(Rr + ivec3(0,0,1),lo,hi),R)).y
                   -TDIn_U(0, flatten3(clamp(Rr + ivec3(0,0,-1),lo,hi),R)).y) * inv2h.z;
    float uR_x_z = (TDIn_U(0, flatten3(clamp(Rr + ivec3(0,0,1),lo,hi),R)).x
                   -TDIn_U(0, flatten3(clamp(Rr + ivec3(0,0,-1),lo,hi),R)).x) * inv2h.z;
    float wR_x_x = (uRR.z - uR.z) * inv2h.x;
    float vR_x_x = (uRR.y - uR.y) * inv2h.x;
    float uR_x_y = (TDIn_U(0, flatten3(clamp(Rr + ivec3(0,1,0),lo,hi),R)).x
                   -TDIn_U(0, flatten3(clamp(Rr + ivec3(0,-1,0),lo,hi),R)).x) * inv2h.y;
    vec3 omegaR = vec3(wR_z_y - vR_y_z, uR_x_z - wR_x_x, vR_x_x - uR_x_y);

    ivec3 DD = clamp(D + ivec3(0,-1,0), lo, hi);
    vec3 uDD = TDIn_U(0, flatten3(DD, R));
    float wD_y_y = (uD.z - uDD.z) * inv2h.y;
    float vD_y_z = (TDIn_U(0, flatten3(clamp(D + ivec3(0,0,1),lo,hi),R)).y
                   -TDIn_U(0, flatten3(clamp(D + ivec3(0,0,-1),lo,hi),R)).y) * inv2h.z;
    float uD_x_z = (TDIn_U(0, flatten3(clamp(D + ivec3(0,0,1),lo,hi),R)).x
                   -TDIn_U(0, flatten3(clamp(D + ivec3(0,0,-1),lo,hi),R)).x) * inv2h.z;
    float wD_x_x = (TDIn_U(0, flatten3(clamp(D + ivec3(1,0,0),lo,hi),R)).z
                   -TDIn_U(0, flatten3(clamp(D + ivec3(-1,0,0),lo,hi),R)).z) * inv2h.x;
    float vD_x_x = (TDIn_U(0, flatten3(clamp(D + ivec3(1,0,0),lo,hi),R)).y
                   -TDIn_U(0, flatten3(clamp(D + ivec3(-1,0,0),lo,hi),R)).y) * inv2h.x;
    float uD_x_y = (uD.x - uDD.x) * inv2h.y;
    vec3 omegaD = vec3(wD_y_y - vD_y_z, uD_x_z - wD_x_x, vD_x_x - uD_x_y);

    ivec3 UU = clamp(Uu + ivec3(0,1,0), lo, hi);
    vec3 uUU = TDIn_U(0, flatten3(UU, R));
    float wU_y_y = (uUU.z - uU.z) * inv2h.y;
    float vU_y_z = (TDIn_U(0, flatten3(clamp(Uu + ivec3(0,0,1),lo,hi),R)).y
                   -TDIn_U(0, flatten3(clamp(Uu + ivec3(0,0,-1),lo,hi),R)).y) * inv2h.z;
    float uU_x_z = (TDIn_U(0, flatten3(clamp(Uu + ivec3(0,0,1),lo,hi),R)).x
                   -TDIn_U(0, flatten3(clamp(Uu + ivec3(0,0,-1),lo,hi),R)).x) * inv2h.z;
    float wU_x_x = (TDIn_U(0, flatten3(clamp(Uu + ivec3(1,0,0),lo,hi),R)).z
                   -TDIn_U(0, flatten3(clamp(Uu + ivec3(-1,0,0),lo,hi),R)).z) * inv2h.x;
    float vU_x_x = (TDIn_U(0, flatten3(clamp(Uu + ivec3(1,0,0),lo,hi),R)).y
                   -TDIn_U(0, flatten3(clamp(Uu + ivec3(-1,0,0),lo,hi),R)).y) * inv2h.x;
    float uU_x_y = (uUU.x - uU.x) * inv2h.y;
    vec3 omegaU = vec3(wU_y_y - vU_y_z, uU_x_z - wU_x_x, vU_x_x - uU_x_y);

    ivec3 BB = clamp(B + ivec3(0,0,-1), lo, hi);
    vec3 uBB = TDIn_U(0, flatten3(BB, R));
    float wB_z_y = (TDIn_U(0, flatten3(clamp(B + ivec3(0,1,0),lo,hi),R)).z
                   -TDIn_U(0, flatten3(clamp(B + ivec3(0,-1,0),lo,hi),R)).z) * inv2h.y;
    float vB_y_z = (uB.y - uBB.y) * inv2h.z;
    float uB_x_z = (uB.x - uBB.x) * inv2h.z;
    float wB_x_x = (TDIn_U(0, flatten3(clamp(B + ivec3(1,0,0),lo,hi),R)).z
                   -TDIn_U(0, flatten3(clamp(B + ivec3(-1,0,0),lo,hi),R)).z) * inv2h.x;
    float vB_x_x = (TDIn_U(0, flatten3(clamp(B + ivec3(1,0,0),lo,hi),R)).y
                   -TDIn_U(0, flatten3(clamp(B + ivec3(-1,0,0),lo,hi),R)).y) * inv2h.x;
    float uB_x_y = (TDIn_U(0, flatten3(clamp(B + ivec3(0,1,0),lo,hi),R)).x
                   -TDIn_U(0, flatten3(clamp(B + ivec3(0,-1,0),lo,hi),R)).x) * inv2h.y;
    vec3 omegaB = vec3(wB_z_y - vB_y_z, uB_x_z - wB_x_x, vB_x_x - uB_x_y);

    ivec3 FF = clamp(F + ivec3(0,0,1), lo, hi);
    vec3 uFF = TDIn_U(0, flatten3(FF, R));
    float wF_z_y = (TDIn_U(0, flatten3(clamp(F + ivec3(0,1,0),lo,hi),R)).z
                   -TDIn_U(0, flatten3(clamp(F + ivec3(0,-1,0),lo,hi),R)).z) * inv2h.y;
    float vF_y_z = (uFF.y - uF.y) * inv2h.z;
    float uF_x_z = (uFF.x - uF.x) * inv2h.z;
    float wF_x_x = (TDIn_U(0, flatten3(clamp(F + ivec3(1,0,0),lo,hi),R)).z
                   -TDIn_U(0, flatten3(clamp(F + ivec3(-1,0,0),lo,hi),R)).z) * inv2h.x;
    float vF_x_x = (TDIn_U(0, flatten3(clamp(F + ivec3(1,0,0),lo,hi),R)).y
                   -TDIn_U(0, flatten3(clamp(F + ivec3(-1,0,0),lo,hi),R)).y) * inv2h.x;
    float uF_x_y = (TDIn_U(0, flatten3(clamp(F + ivec3(0,1,0),lo,hi),R)).x
                   -TDIn_U(0, flatten3(clamp(F + ivec3(0,-1,0),lo,hi),R)).x) * inv2h.y;
    vec3 omegaF = vec3(wF_z_y - vF_y_z, uF_x_z - wF_x_x, vF_x_x - uF_x_y);

    // --- gradient de |ω|
    float magL = length(omegaL), magR = length(omegaR);
    float magD = length(omegaD), magU = length(omegaU);
    float magB = length(omegaB), magF = length(omegaF);

    vec3 gradMag = vec3((magR - magL)*inv2h.x,
                        (magU - magD)*inv2h.y,
                        (magF - magB)*inv2h.z);

    float g = length(gradMag);
    vec3 N  = (g > 1e-9) ? (gradMag / g) : vec3(0.0);

    // --- confinement de vorticité avec seuils
    float sCurl = smoothstep(curlMin, 2.0*curlMin, length(omega));
    float sGrad = smoothstep(gradMin, 2.0*gradMin, g);
    vec3 f_conf = (vcStrength * sCurl * sGrad) * cross(N, omega);

    // --- flottabilité
    vec3 jhat   = normalize(buoyDir);
    vec3 f_buoy = sigma * (T - T0) * jhat;

    // --- total
    u += dt * (Fext + f_buoy + f_conf);

    // --- DAMPING (linéaire + quadratique)
    float lin  = max(linDamp,  0.0);
    float quad = max(quadDamp, 0.0);
    float spd0 = length(u);
    float denom = 1.0 + lin*dt + quad*spd0*dt;
    u /= denom;

    // --- SOFT CAP (si activé) ---
    if (limitSpeed == 1u && vSoftCap > 0.0){
        float spd = length(u);
        float upper = vSoftCap * (1.0 + max(softCapKnee, 0.0)); // knee additif
        float k = smoothstep(vSoftCap, upper, spd);
        float scale = mix(1.0, vSoftCap / max(spd, 1e-9), k);
        u *= scale;
    }

    // --- BC no-slip
    if (TDIn_Flag() == 1u){
        vec3  bnd  = TDIn_BndN();
        ivec3 Ii   = clamp(I - ivec3(int(bnd.x),int(bnd.y),int(bnd.z)), lo, hi);
        vec3 u_in  = TDIn_U(0, flatten3(Ii, R));
        vec3 flip  = vec3(bnd.x != 0.0 ? -1.0 : 1.0,
                          bnd.y != 0.0 ? -1.0 : 1.0,
                          bnd.z != 0.0 ? -1.0 : 1.0);
        u = u_in * flip;
    }

    U[id] = u;
}
