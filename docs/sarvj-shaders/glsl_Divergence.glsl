// helpers
uint flatten3(ivec3 c, uint R){ return uint(c.x) + R*(uint(c.y) + R*uint(c.z)); }

void main(){
    const uint id = TDIndex(); if (id >= TDNumElements()) return;

    if (TDIn_Flag() == 1u) { Div[id] = 0.0; return; }

    // indices 3D
    uint R = max(SimRes,1u);
    uint i =  id              % R;
    uint j = (id / R)         % R;
    uint k =  id / (R*R);
    ivec3 I = ivec3(int(i),int(j),int(k));
    ivec3 lo=ivec3(0), hi=ivec3(int(R)-1);

    // voisins
    ivec3 L = clamp(I + ivec3(-1,0,0), lo, hi);
    ivec3 Rr= clamp(I + ivec3( 1,0,0), lo, hi);
    ivec3 D = clamp(I + ivec3(0,-1,0), lo, hi);
    ivec3 Uu= clamp(I + ivec3(0, 1,0), lo, hi);
    ivec3 B = clamp(I + ivec3(0,0,-1), lo, hi);
    ivec3 F = clamp(I + ivec3(0,0, 1), lo, hi);

    vec3 uL = TDIn_U(0, flatten3(L,  R));
    vec3 uR = TDIn_U(0, flatten3(Rr, R));
    vec3 uD = TDIn_U(0, flatten3(D,  R));
    vec3 uU = TDIn_U(0, flatten3(Uu, R));
    vec3 uB = TDIn_U(0, flatten3(B,  R));
    vec3 uF = TDIn_U(0, flatten3(F,  R));

    // métriques
    vec3 size    = vec3(SimSizex,SimSizey,SimSizez);
    vec3 h       = size / float(R);
    vec3 halfrdx = 0.5 / h;

    float div = halfrdx.x*(uR.x - uL.x)
              + halfrdx.y*(uU.y - uD.y)
              + halfrdx.z*(uF.z - uB.z);

    // write
    Div[id] = div;
}
