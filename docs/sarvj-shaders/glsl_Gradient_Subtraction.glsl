uint flatten3(ivec3 c, uint R){ return uint(c.x) + R*(uint(c.y) + R*uint(c.z)); }

void main(){
    const uint id = TDIndex(); if (id >= TDNumElements()) return;

    // indices 3D
    uint R = max(SimRes,1u);
    uint i =  id              % R;
    uint j = (id / R)         % R;
    uint k =  id / (R*R);
    ivec3 I = ivec3(int(i),int(j),int(k));
    ivec3 lo=ivec3(0), hi=ivec3(int(R)-1);

    // métriques
    vec3 size    = vec3(SimSizex,SimSizey,SimSizez);
    vec3 h       = size / float(R);
    vec3 halfrdx = 0.5 / h;

    // BC_U sur la couronne (no-slip)
    if (TDIn_Flag() == 1u){
        vec3  bnd = TDIn_BndN();
        ivec3 Ii  = clamp(I - ivec3(int(bnd.x),int(bnd.y),int(bnd.z)), lo, hi);
        vec3 u_in = TDIn_U(0, flatten3(Ii, R));
        vec3 flip = vec3(bnd.x != 0.0 ? -1.0 : 1.0,
                         bnd.y != 0.0 ? -1.0 : 1.0,
                         bnd.z != 0.0 ? -1.0 : 1.0);
        U[id] = u_in * flip;
        return;
    }

    // voisins pression
    ivec3 L = clamp(I + ivec3(-1,0,0), lo, hi);
    ivec3 Rr= clamp(I + ivec3( 1,0,0), lo, hi);
    ivec3 D = clamp(I + ivec3(0,-1,0), lo, hi);
    ivec3 Uu= clamp(I + ivec3(0, 1,0), lo, hi);
    ivec3 B = clamp(I + ivec3(0,0,-1), lo, hi);
    ivec3 F = clamp(I + ivec3(0,0, 1), lo, hi);

    float pL = TDIn_Press(0, flatten3(L,  R));
    float pR = TDIn_Press(0, flatten3(Rr, R));
    float pD = TDIn_Press(0, flatten3(D,  R));
    float pU = TDIn_Press(0, flatten3(Uu, R));
    float pB = TDIn_Press(0, flatten3(B,  R));
    float pF = TDIn_Press(0, flatten3(F,  R));

    vec3 gradP = vec3( halfrdx.x * (pR - pL),
                       halfrdx.y * (pU - pD),
                       halfrdx.z * (pF - pB) );

    vec3 u = TDIn_U() - gradP;

    U[id] = u;
}
