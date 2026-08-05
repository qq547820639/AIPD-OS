#!/usr/bin/env python3
"""Minimal faceted-BREP STEP writer and structural parser.

This fallback supports internal CAD-L0..L3 digital prototypes when an OpenCASCADE
runtime or provider CAD skill is unavailable. It is not a replacement for native
feature-history CAD, analytic B-Rep, GD&T, or tooling release.
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any

class FacetedStepWriter:
    def __init__(self): self.entities=[]
    def add(self, body:str)->int: self.entities.append(body); return len(self.entities)
    @staticmethod
    def ref(i:int)->str: return f"#{i}"

    def write(self, meshes:list[dict[str,Any]], path:Path, *, product_name:str="AIPD ASSEMBLY", timestamp:str="1970-01-01T00:00:00+00:00")->dict:
        app=self.add("APPLICATION_CONTEXT('configuration controlled 3d designs of mechanical parts and assemblies')")
        self.add(f"APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,{self.ref(app)})")
        design=self.add(f"DESIGN_CONTEXT('',{self.ref(app)},'design')")
        mech=self.add(f"MECHANICAL_CONTEXT('',{self.ref(app)},'mechanical')")
        ul=self.add("(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))")
        ua=self.add("(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.))")
        us=self.add("(NAMED_UNIT(*)SOLID_ANGLE_UNIT()SI_UNIT($,.STERADIAN.))")
        unc=self.add(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-6),{self.ref(ul)},'distance_accuracy_value','confusion accuracy')")
        ctx=self.add(f"(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({self.ref(unc)}))GLOBAL_UNIT_ASSIGNED_CONTEXT(({self.ref(ul)},{self.ref(ua)},{self.ref(us)}))REPRESENTATION_CONTEXT('AIPD Context','3D'))")
        solids=[]; faces=0; points=0
        for item in meshes:
            name=str(item['name']).replace("'","")
            vertices=item['vertices']; triangles=item['faces']
            vrefs=[]
            for v in vertices:
                vrefs.append(self.add("CARTESIAN_POINT('',("+','.join(f'{float(x):.8f}' for x in v)+"))"))
            points += len(vrefs); frefs=[]
            for face in triangles:
                loop=self.add("POLY_LOOP('',("+','.join(self.ref(vrefs[int(i)]) for i in face)+"))")
                bound=self.add(f"FACE_OUTER_BOUND('',{self.ref(loop)},.T.)")
                frefs.append(self.add(f"FACE('',({self.ref(bound)}))"))
            faces += len(frefs)
            shell=self.add("CLOSED_SHELL('',("+','.join(self.ref(i) for i in frefs)+"))")
            solids.append(self.add(f"FACETED_BREP('{name}',{self.ref(shell)})"))
        rep=self.add("SHAPE_REPRESENTATION('AIPD ASSEMBLY',("+','.join(self.ref(i) for i in solids)+f"),{self.ref(ctx)})")
        product=self.add(f"PRODUCT('{product_name}','{product_name}','',({self.ref(mech)}))")
        form=self.add(f"PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('1','Digital prototype',{self.ref(product)},.NOT_KNOWN.)")
        definition=self.add(f"PRODUCT_DEFINITION('design','',{self.ref(form)},{self.ref(design)})")
        pshape=self.add(f"PRODUCT_DEFINITION_SHAPE('','',{self.ref(definition)})")
        self.add(f"SHAPE_DEFINITION_REPRESENTATION({self.ref(pshape)},{self.ref(rep)})")
        header=["ISO-10303-21;","HEADER;","FILE_DESCRIPTION(('AIPD faceted BREP'),'2;1');",f"FILE_NAME('{path.name}','{timestamp}',('AIPD'),('AIPD'),'local fallback','AIPD-OS','internal digital prototype');","FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));","ENDSEC;","DATA;"]
        data=[f"#{i}={body};" for i,body in enumerate(self.entities,1)]
        path.write_text('\n'.join(header+data+["ENDSEC;","END-ISO-10303-21;",""]),encoding='ascii')
        return {'entities':len(self.entities),'solids':len(solids),'faces':faces,'points':points}

def parse_step(path:Path)->dict:
    text=path.read_text(encoding='ascii')
    entities={int(m.group(1)):m.group(2).strip() for m in re.finditer(r"#(\d+)=(.*?);\s*",text,re.S)}
    refs={int(r) for body in entities.values() for r in re.findall(r"#(\d+)",body)}
    return {
      'header_valid':text.startswith('ISO-10303-21;') and text.rstrip().endswith('END-ISO-10303-21;'),
      'entity_count':len(entities),'faceted_brep_count':text.count('FACETED_BREP('),'closed_shell_count':text.count('CLOSED_SHELL('),
      'triangle_loop_count':text.count('POLY_LOOP('),'undefined_references':sorted(refs-set(entities))
    }
