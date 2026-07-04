#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LBD to FiCR RDF Converter
LBD 到 FiCR RDF 转换器

功能 Features:
1. 动态从 ficr_tbox.ttl 加载所有属性定义
   Dynamically load all property definitions from ficr_tbox.ttl
2. 映射 props: 属性到 ficr: 属性
   Map props: properties to ficr: properties  
3. 保留 BOT 关系属性
   Preserve BOT relationship properties
4. 支持单文件和批量转换
   Support single file and batch conversion
"""

import sys
import os
import re
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, XSD
from typing import Set, Dict, Optional, Tuple

# 命名空间定义 Namespace Definitions
FICR = Namespace("https://w3id.org/bam/ficr#")
BOT = Namespace("https://w3id.org/bot#")
BEO  = Namespace("https://pi.pauwel.be/voc/buildingelement#")
FURN = Namespace("http://pi.pauwel.be/voc/furniture#")
MEP  = Namespace("http://pi.pauwel.be/voc/distributionelement#")
PROPS = Namespace("http://lbd.arch.rwth-aachen.de/props#")
# NOTE: IFC 命名空间用于匹配 IfcOpeningElement 等 IFC 原始类型
IFC = Namespace("https://standards.buildingsmart.org/IFC/DEV/IFC2x3/TC1/OWL#")


class LBDToFiCRConverter:
    """LBD 到 FiCR 的 RDF 转换器"""
    
    def __init__(self, ontology_path: str = "FiCR_ontology/ficr_tbox.ttl"):
        """初始化转换器"""
        self.ontology_path = ontology_path
        self.ontology_graph = Graph()
        self.source_graph = Graph()
        self.target_graph = Graph()
        
        # 动态加载的属性集合
        self.object_properties: Set[URIRef] = set()
        self.data_properties: Set[URIRef] = set()
        self.annotation_properties: Set[URIRef] = set()
        
        # 配置映射
        self.property_mapping = self._create_property_mapping()
        self.class_mapping = self._create_class_mapping()
        
        # 统计信息
        self.stats = {
            'total_triples': 0,
            'converted_properties': 0,
            'preserved_relations': 0,
            'unmapped_properties': 0,
            'class_counts': {},
            'buildings_classified': 0,
            'storeys_classified': 0,
            'spaces_classified_omniclass': 0,
            'spaces_classified_text': 0,
            'spaces_unclassified': 0,
        }
    
    def _create_property_mapping(self) -> Dict[str, str]:
        """创建属性映射配置

        Verified against ficr_tbox.ttl v0.16.0.

        Removed mappings (not in TBox v0.16.0):
          - props:area_property_simple was ficr:hasFloorArea → use ficr:hasArea
          - props:heightOffsetFromLevel_property_simple was ficr:hasHeightOffset
          - props:roomBounding_property_simple was ficr:isRoomBounding
          - props:height_property_simple was ficr:hasHeight
            REMOVED in v0.15.0. In the LBD source this field appears only on
            furniture instances (cabinets), never on walls or spaces, so the
            mapping was also semantically incorrect.

        Added mappings (v0.15.0):
          - props:unboundedHeight_property_simple → ficr:hasStoreyHeight
            Carries floor-to-ceiling room height on Space instances (e.g. 2.6 m).
        """
        return {
            'props:globalIdIfcRoot_attribute_simple':  'ficr:hasID',
            'props:volume_property_simple':            'ficr:hasVolume',
            'props:length_property_simple':            'ficr:hasLength',
            'props:width_property_simple':             'ficr:hasWidth',
            'props:area_property_simple':              'ficr:hasArea',
            'props:thickness_property_simple':         'ficr:hasThickness',
            'props:elevation_property_simple':         'ficr:hasElevation',
            'props:unboundedHeight_property_simple':   'ficr:hasStoreyHeight',  # Change 3
            'props:isExternal_property_simple':        'ficr:isExternal',
            'props:loadBearing_property_simple':       'ficr:isLoadBearing',
        }
    
    def _create_class_mapping(self) -> Dict[str, str]:
        """创建类映射配置
        
        Note on Slab (v0.16.0): ficr:Slab is now rdfs:subClassOf ficr:Floor AND ficr:StructuralElement.
        Typing instances as ficr:Slab is therefore more precise than ficr:Floor and still
        propagates upward to Floor via subClassOf.
        """
        return {
            'beo:Wall': 'ficr:Wall',
            'beo:Slab': 'ficr:FloorSlab',          # was ficr:Slab — FloorSlab subclass (v0.15.0)
            'beo:Slab-FLOOR': 'ficr:FloorSlab',   # was ficr:Slab — same reason
            'beo:Roof': 'ficr:RoofSlab',           # previously unmapped
            'beo:Slab-ROOF': 'ficr:RoofSlab',      # previously unmapped
            'beo:Covering': 'ficr:Ceiling',
            'beo:Covering-CEILING': 'ficr:Ceiling',
            'beo:Window': 'ficr:Window',
            'beo:Door': 'ficr:Doorset',
            'beo:Stair': 'ficr:Stair',
            'beo:StairFlight': 'ficr:StairFlight',
            'beo:Railing': 'ficr:Railing',
            'beo:Railing-NOTDEFINED': 'ficr:Railing',  # Railing 子类型统一映射
            'beo:Beam': 'ficr:Beam',
            'beo:Footing': 'ficr:WallFoundation',       # IFC Footing → ficr:WallFoundation
            'beo:Footing-STRIP_FOOTING': 'ficr:WallFoundation',  # 条形基础 → ficr:WallFoundation
            # beo:Member: removed from static mapping — disambiguated in _classify_members()
            # (Mullion → bot:Element, Stair/stringer → ficr:StairFlight, other → ficr:Beam)
            'beo:CurtainWall': 'ficr:Wall',              # 幕墙体系 → ficr:Wall (无 ficr:CurtainWall)
            'beo:Column': 'ficr:Column',                 # 柱 → ficr:Column
            'beo:Plate': 'ficr:FloorSlab',               # 结构板 → ficr:FloorSlab
            'beo:Slab-LANDING': 'ficr:FloorSlab',        # 楼梯平台板 → ficr:FloorSlab
            'furn:Furniture': 'ficr:Furnishings',
        }
    
    def _load_ontology(self) -> None:
        """从 ficr_tbox.ttl 动态加载所有属性定义"""
        print(f"\n正在加载 ontology: {self.ontology_path}")
        print(f"Loading ontology: {self.ontology_path}")
        
        if not os.path.exists(self.ontology_path):
            raise FileNotFoundError(f"Ontology 文件不存在: {self.ontology_path}")
        
        self.ontology_graph.parse(self.ontology_path, format="turtle")
        
        # 提取所有属性定义
        for prop in self.ontology_graph.subjects(RDF.type, OWL.ObjectProperty):
            self.object_properties.add(prop)
        
        for prop in self.ontology_graph.subjects(RDF.type, OWL.DatatypeProperty):
            self.data_properties.add(prop)
        
        for prop in self.ontology_graph.subjects(RDF.type, OWL.AnnotationProperty):
            self.annotation_properties.add(prop)
        
        # 应用优先级：Object Property > Data Property > Annotation Property
        self.annotation_properties -= self.object_properties
        self.annotation_properties -= self.data_properties
        
        print(f"  - Object Properties: {len(self.object_properties)}")
        print(f"  - Data Properties: {len(self.data_properties)}")
        print(f"  - Annotation Properties: {len(self.annotation_properties)}")
    
    def load_source(self, input_file: str) -> None:
        """加载源 RDF 文件"""
        print(f"\n正在加载源文件: {input_file}")
        print(f"Loading source file: {input_file}")
        
        self.source_graph = Graph()
        self.source_graph.parse(input_file, format="turtle")
        
        print(f"已加载 {len(self.source_graph)} 条三元组")
        print(f"Loaded {len(self.source_graph)} triples")
    
    def _setup_namespaces(self) -> None:
        """设置目标图的命名空间"""
        self.target_graph.bind('ficr', FICR)
        self.target_graph.bind('bot', BOT)
        self.target_graph.bind('rdfs', RDFS)
        self.target_graph.bind('xsd', XSD)
        self.target_graph.bind('owl', OWL)
    
    def _map_class(self, original_class: URIRef) -> URIRef:
        """映射类 URI"""
        class_str = original_class.n3(self.source_graph.namespace_manager)
        
        if class_str in self.class_mapping:
            ficr_class_str = self.class_mapping[class_str]
            if ':' in ficr_class_str:
                prefix, local = ficr_class_str.split(':', 1)
                if prefix == 'ficr':
                    return FICR[local]
        
        # NOTE: IfcOpeningElement → ficr:Opening，使用完整 URI 匹配
        if str(original_class) == str(IFC['IfcOpeningElement']):
            return FICR['Opening']
        
        # 保留 bot: 类不变
        if str(original_class).startswith(str(BOT)):
            return original_class

        # BEO / FURN / MEP 未映射的物理构件 → 降级为 bot:Element
        if (str(original_class).startswith(str(BEO)) or
                str(original_class).startswith(str(FURN)) or
                str(original_class).startswith(str(MEP))):
            return BOT.Element

        return original_class
    
    def _convert_data_value(self, value, ficr_prop: URIRef) -> Literal:
        """转换数据值到正确的 XSD 类型"""
        value_str = str(value)
        
        # 布尔值
        if value_str.lower() in ['true', 'false']:
            return Literal(value_str.lower() == 'true', datatype=XSD.boolean)
        
        # 数字值（固定3位小数，使用 xsd:decimal）
        try:
            num = float(value_str)
            formatted = f"{num:.3f}"
            return Literal(formatted, datatype=XSD.decimal)
        except ValueError:
            pass
        
        # 字符串
        return Literal(value_str, datatype=XSD.string)
    
    def _convert_property(self, subject: URIRef, prop: URIRef, value) -> Optional[Tuple[URIRef, any]]:
        """转换单个属性"""
        prop_str = prop.n3(self.source_graph.namespace_manager)
        
        # 1. 检查映射表
        if prop_str in self.property_mapping:
            ficr_prop_str = self.property_mapping[prop_str]
            if ':' in ficr_prop_str:
                prefix, local = ficr_prop_str.split(':', 1)
                if prefix == 'ficr':
                    ficr_prop = FICR[local]
                    
                    if ficr_prop in self.data_properties:
                        converted_value = self._convert_data_value(value, ficr_prop)
                        self.stats['converted_properties'] += 1
                        return ficr_prop, converted_value
                    elif ficr_prop in self.object_properties:
                        self.stats['preserved_relations'] += 1
                        return ficr_prop, value
        
        # 2. 检查是否是 ontology 中定义的 Object Property
        if prop in self.object_properties:
            self.stats['preserved_relations'] += 1
            return prop, value
        
        # 3. 检查是否是 ontology 中定义的 Data Property
        if prop in self.data_properties:
            converted_value = self._convert_data_value(value, prop)
            self.stats['converted_properties'] += 1
            return prop, converted_value
        
        # 4. rdfs:label 保留
        if prop == RDFS.label:
            return prop, value
        
        # 5. 其他未映射的属性跳过
        self.stats['unmapped_properties'] += 1
        return None
    
    def _classify_building(self) -> None:
        """根据楼层数推断建筑子类型 (Change B)。

        storey count ≥ 2 → ficr:MultiStoreyBuilding
        storey count = 1 → ficr:SingleStoreyBuilding
        storey count = 0 → skip
        """
        print("\n正在推断建筑子类型 ...")
        print("Classifying buildings by storey count ...")

        for building in list(self.target_graph.subjects(RDF.type, BOT.Building)):
            storeys = list(self.target_graph.objects(building, BOT.hasStorey))
            n = len(storeys)
            if n >= 2:
                self.target_graph.remove((building, RDF.type, BOT.Building))
                self.target_graph.add((building, RDF.type, FICR.MultiStoreyBuilding))
                self.stats['buildings_classified'] += 1
                print(f"  {building} → MultiStoreyBuilding ({n} storeys)")
            elif n == 1:
                self.target_graph.remove((building, RDF.type, BOT.Building))
                self.target_graph.add((building, RDF.type, FICR.SingleStoreyBuilding))
                self.stats['buildings_classified'] += 1
                print(f"  {building} → SingleStoreyBuilding ({n} storey)")

            # P4: 写入楼层数
            if n > 0:
                self.target_graph.add((
                    building, FICR.hasNumberOfStoreys,
                    Literal(n, datatype=XSD.integer)
                ))

            # v0.16.0: building-level computed properties
            storey_data = []  # list of (storey, elevation, storey_height)
            for s in storeys:
                elev = self.target_graph.value(s, FICR.hasElevation)
                sh = self.target_graph.value(s, FICR.hasStoreyHeight)
                try:
                    e = float(str(elev)) if elev is not None else None
                except (ValueError, TypeError):
                    e = None
                try:
                    h = float(str(sh)) if sh is not None else None
                except (ValueError, TypeError):
                    h = None
                storey_data.append((s, e, h))

            # hasBuildingHeight = max(elev + height) - min(elev)
            tops = [e + h for _, e, h in storey_data if e is not None and h is not None]
            elevs = [e for _, e, _ in storey_data if e is not None]
            if tops and elevs:
                bldg_height = max(tops) - min(elevs)
                self.target_graph.add((
                    building, FICR.hasBuildingHeight,
                    Literal(f"{bldg_height:.3f}", datatype=XSD.decimal)
                ))
                print(f"  {building} hasBuildingHeight={bldg_height:.3f}")

            # hasTopStoreyFloorHeight / hasTopStoreyHeight
            # topmost above-ground storey = highest elevation among elev >= 0
            above_ground = [(s, e, h) for s, e, h in storey_data if e is not None and e >= 0.0]
            if above_ground:
                above_ground.sort(key=lambda x: x[1])
                _, top_elev, top_height = above_ground[-1]
                self.target_graph.add((
                    building, FICR.hasTopStoreyFloorHeight,
                    Literal(f"{top_elev:.3f}", datatype=XSD.decimal)
                ))
                print(f"  {building} hasTopStoreyFloorHeight={top_elev:.3f}")
                if top_height is not None:
                    self.target_graph.add((
                        building, FICR.hasTopStoreyHeight,
                        Literal(f"{top_height:.3f}", datatype=XSD.decimal)
                    ))
                    print(f"  {building} hasTopStoreyHeight={top_height:.3f}")

            # hasCombinedGrossFloorArea = sum of all space hasArea in this building
            total_area = 0.0
            has_any_area = False
            for s in storeys:
                for space in self.target_graph.objects(s, BOT.hasSpace):
                    area_val = self.target_graph.value(space, FICR.hasArea)
                    if area_val is not None:
                        try:
                            total_area += float(str(area_val))
                            has_any_area = True
                        except (ValueError, TypeError):
                            pass
            if has_any_area:
                self.target_graph.add((
                    building, FICR.hasCombinedGrossFloorArea,
                    Literal(f"{total_area:.3f}", datatype=XSD.decimal)
                ))
                print(f"  {building} hasCombinedGrossFloorArea={total_area:.3f}")

    def _classify_storeys(self) -> None:
        """根据标高推断楼层子类型 (Change C)。

        elevation ≥ 0.0 → ficr:GroundAndAboveStorey
        elevation < 0.0 → ficr:BasementStorey
        """
        print("\n正在推断楼层子类型 ...")
        print("Classifying storeys by elevation ...")

        for storey in list(self.target_graph.subjects(RDF.type, BOT.Storey)):
            elev_val = self.target_graph.value(storey, FICR.hasElevation)
            if elev_val is None:
                continue
            try:
                elev = float(str(elev_val))
            except (ValueError, TypeError):
                continue

            if elev >= 0.0:
                self.target_graph.remove((storey, RDF.type, BOT.Storey))
                self.target_graph.add((storey, RDF.type, FICR.GroundAndAboveStorey))
                self.target_graph.add((storey, FICR.isAboveGround, Literal(True, datatype=XSD.boolean)))
                self.stats['storeys_classified'] += 1
                print(f"  {storey} elev={elev:.3f} → GroundAndAboveStorey (isAboveGround=true)")
            else:
                self.target_graph.remove((storey, RDF.type, BOT.Storey))
                self.target_graph.add((storey, RDF.type, FICR.BasementStorey))
                self.target_graph.add((storey, FICR.isAboveGround, Literal(False, datatype=XSD.boolean)))
                self.stats['storeys_classified'] += 1
                print(f"  {storey} elev={elev:.3f} → BasementStorey (isAboveGround=false)")

    def _classify_members(self) -> None:
        """基于 rdfs:label / objectType 消歧 beo:Member 实例 (P0)。

        beo:Member 在 IFC 中既可以是楼梯构件（stringer）也可以是幕墙竖框
        （mullion）等。静态映射无法区分，因此从 class_mapping 移除后在此
        根据源图中的标签和 objectType 属性进行分类：
          - label 含 "Stair" 或 objectType 含 "stringer" → ficr:StairFlight
          - label 含 "Mullion" → bot:Element（保持不变）
          - 其余 → ficr:Beam
        """
        print("\n正在分类 beo:Member 实例 ...")
        print("Classifying beo:Member instances ...")

        stair_count = mullion_count = beam_count = 0
        member_type = BEO['Member']
        obj_type_prop = PROPS['objectTypeIfcObject_attribute_simple']

        for subject in list(self.source_graph.subjects(RDF.type, member_type)):
            label = str(self.source_graph.value(subject, RDFS.label) or '')
            obj_type = str(self.source_graph.value(subject, obj_type_prop) or '')

            label_lower = label.lower()
            obj_type_lower = obj_type.lower()

            if 'stair' in label_lower or 'stringer' in obj_type_lower:
                self.target_graph.remove((subject, RDF.type, BOT.Element))
                self.target_graph.add((subject, RDF.type, FICR.StairFlight))
                stair_count += 1
            elif 'mullion' in label_lower:
                # 保持 bot:Element（幕墙竖框组件）
                mullion_count += 1
            else:
                self.target_graph.remove((subject, RDF.type, BOT.Element))
                self.target_graph.add((subject, RDF.type, FICR.Beam))
                beam_count += 1

        self.stats['members_stair'] = stair_count
        self.stats['members_mullion'] = mullion_count
        self.stats['members_beam'] = beam_count
        print(f"  StairFlight: {stair_count}, Mullion(bot:Element): {mullion_count}, Beam: {beam_count}")

    def _classify_spaces(self) -> None:
        """根据 OmniClass 编码或描述文本推断空间子类型和用途 (Change D)。

        Layer 1: OmniClass code (most-specific-first prefix match)
        Layer 2: categoryDescription keyword match (case-insensitive)
        Layer 3: fallback — no subclass written
        """
        print("\n正在推断空间子类型和用途 ...")
        print("Classifying spaces by OmniClass / description ...")

        # Layer 1 — OmniClass prefix rules (longest prefix first)
        # Sorted at runtime by prefix length descending for most-specific-first matching.
        # P1: expanded from 9 → 14 rules; refined 13-11, 13-85; added 13-15, 13-41 41, 13-75
        omniclass_rules = [
            # ── 13-11: Assembly/Meeting spaces ──
            ("13-11 19",    "RoomSpace",    "Kitchen"),           # Food Preparation only
            ("13-11",       "RoomSpace",    "HabitableRoom"),     # Reception, Conference, Classroom
            # ── 13-15: Office/Administrative (NEW) ──
            ("13-15",       "RoomSpace",    "HabitableRoom"),     # Office, Lab, Clean Room, Copy Room
            # ── 13-41: Personal care / Medical ──
            ("13-41 41",    "RoomSpace",    "HabitableRoom"),     # Healing/Medical (Exam, Scanning, Treatment)
            ("13-41",       "RoomSpace",    "Bathroom"),          # Restroom, Dressing Room, Grooming
            # ── 13-51: Residential/Habitable ──
            ("13-51 24 11", "RoomSpace",    "HabitableRoom"),
            ("13-51 24",    "RoomSpace",    "HabitableRoom"),
            ("13-51 21",    "RoomSpace",    "HabitableRoom"),
            ("13-51",       "RoomSpace",    "HabitableRoom"),
            # ── 13-75: Storage (NEW) ──
            ("13-75",       "RoomSpace",    "ServiceUsage"),      # Storage, Soiled Storage, Hazardous
            # ── 13-81: Facility Service ──
            ("13-81 31",    "RoomSpace",    "ServiceUsage"),
            ("13-81",       "RoomSpace",    "ServiceUsage"),
            # ── 13-85: Circulation (REFINED) ──
            ("13-85 21",    "StairSpace",   "CirculationUsage"),  # Stairway only
            ("13-85",       "RoomSpace",    "CirculationUsage"),  # Corridor, Vestibule (fallback)
        ]
        # Sort by prefix length descending for most-specific-first matching
        omniclass_rules.sort(key=lambda r: len(r[0]), reverse=True)

        # Layer 2 — keyword rules (first match wins)
        keyword_rules = [
            (["stair", "stairway"],                  "StairSpace",   "CirculationUsage"),
            (["bathroom", "toilet", "wc"],           "RoomSpace",    "Bathroom"),
            (["kitchen"],                            "RoomSpace",    "Kitchen"),
            (["bedroom", "living"],                  "RoomSpace",    "HabitableRoom"),
            (["corridor", "hallway", "hall", "foyer"], "RoomSpace",  "CirculationUsage"),
            (["service", "utility", "plant"],        "RoomSpace",    "ServiceUsage"),
            (["roof"],                               "RoofSpace",    "ServiceUsage"),
            (["shaft", "duct"],                      "ShaftSpace",   "ServiceUsage"),
            (["lift", "elevator"],                   "LiftShaft",    "ServiceUsage"),
            (["atrium"],                             "AtriumSpace",  "HabitableRoom"),
            (["balcony"],                            "BalconySpace", "HabitableRoom"),
            (["cavity", "void"],                     "CavitySpace",  "ServiceUsage"),
        ]

        omni_prop = PROPS['omniClassTableCategory_property_simple']
        desc_prop = PROPS['categoryDescription_property_simple']

        for space in list(self.target_graph.subjects(RDF.type, BOT.Space)):
            subclass_local = None
            usage_local = None

            # Layer 1 — OmniClass code from source graph
            omni_val = self.source_graph.value(space, omni_prop)
            if omni_val is not None:
                omni_str = str(omni_val).strip()
                for prefix, sc, us in omniclass_rules:
                    if omni_str.startswith(prefix):
                        subclass_local = sc
                        usage_local = us
                        break

            # Layer 2 — categoryDescription from source graph
            if subclass_local is None:
                desc_val = self.source_graph.value(space, desc_prop)
                if desc_val is not None:
                    desc_lower = str(desc_val).lower()
                    for keywords, sc, us in keyword_rules:
                        if any(kw in desc_lower for kw in keywords):
                            subclass_local = sc
                            usage_local = us
                            break

            # Track which layer matched
            matched_layer = None
            if subclass_local is not None:
                # If Layer 2 was used, omni_val either was None or didn't match
                # Layer 1 matched only if omni_val produced the result
                if omni_val is not None:
                    omni_str = str(omni_val).strip()
                    if any(omni_str.startswith(p) for p, _, _ in omniclass_rules):
                        matched_layer = 'omniclass'
                if matched_layer is None:
                    matched_layer = 'text'

            # Write triples
            if subclass_local is not None:
                self.target_graph.remove((space, RDF.type, BOT.Space))
                self.target_graph.add((space, RDF.type, FICR[subclass_local]))
                self.target_graph.add((space, FICR.hasSpaceUsage, FICR[usage_local]))
                if matched_layer == 'omniclass':
                    self.stats['spaces_classified_omniclass'] += 1
                else:
                    self.stats['spaces_classified_text'] += 1
                lbl = self.source_graph.value(space, RDFS.label) or space
                print(f"  {lbl} → {subclass_local}, usage={usage_local}")
            else:
                self.stats['spaces_unclassified'] += 1
                lbl = self.source_graph.value(space, RDFS.label) or space
                print(f"  {lbl} → unclassified")

    def _infer_space_adjacency(self) -> None:
        """从共享构件推断空间连通性，写入 bot:adjacentZone 三元组。

        LBD / ifc2lbd 输出中没有 bot:adjacentZone 三元组，但每个空间
        通过 bot:adjacentElement 与其边界构件相连。两个空间若共享同一
        Wall 或 Door 构件，则在水平方向上相邻；若共享同一 Slab / Floor
        构件，则在垂直方向上连通。

        写入规则
        ────────
        水平 (bot:adjacentZone)：
          两空间共享至少一个 Wall 或 Door（Doorset）类型的构件。
          写为双向三元组：spaceA bot:adjacentZone spaceB，且反向同写。
          该属性与 SPARQL 查询中的横向蔓延路径直接对应。

        垂直 (bot:intersectsZone)：  ← Change 4
          两空间共享至少一个 Slab / Floor 类型的构件，且没有共享 Wall。
          使用 TBox v0.16.0 中已声明的 bot:intersectsZone（ObjectProperty,
          domain=Zone, range=Zone），语义上表示"空间在楼板处相互贯通"，
          与水平蔓延路径分开，避免纳入横向火灾扩散计算。

          原 ficr:isVerticallyAdjacentTo 是自造属性，未在 TBox 中声明，
          已在 Change 4 中替换。

        统计信息
        ────────
        adjacency_horizontal: 水平相邻对数量（双向各计 1）
        adjacency_party_wall: 跨单元（A↔B）相邻对数量
        adjacency_vertical:   垂直连通对数量
        """
        print("\n正在推断空间连通性 (bot:adjacentZone / bot:intersectsZone) ...")
        print("Inferring space adjacency from shared elements ...")

        # 收集所有空间及其构件集合（在 SOURCE 图中读取）
        spaces = list(self.source_graph.subjects(RDF.type, BOT.Space))
        space_elements: Dict[URIRef, Set[URIRef]] = {}
        for space in spaces:
            space_elements[space] = set(
                self.source_graph.objects(space, BOT.adjacentElement)
            )

        # 判断构件是否属于 Wall 或 Door 类型（source 图中的 beo: 类型）
        def _has_type_containing(elem: URIRef, keywords) -> bool:
            for t in self.source_graph.objects(elem, RDF.type):
                local = str(t).split('#')[-1].split('/')[-1]
                if any(k in local for k in keywords):
                    return True
            return False

        horiz = vert = party = 0

        for i, spA in enumerate(spaces):
            for spB in spaces[i + 1:]:
                shared = space_elements.get(spA, set()) & space_elements.get(spB, set())
                if not shared:
                    continue

                has_wall_or_door = any(
                    _has_type_containing(e, ('Wall', 'Door')) for e in shared
                )
                has_slab = any(
                    _has_type_containing(e, ('Slab', 'Floor', 'Covering')) for e in shared
                )

                lblA = str(self.source_graph.value(spA, RDFS.label) or '')
                lblB = str(self.source_graph.value(spB, RDFS.label) or '')
                cross_unit = bool(lblA and lblB and lblA[0] != lblB[0])

                if has_wall_or_door:
                    # Horizontal adjacency — bidirectional
                    self.target_graph.add((spA, BOT.adjacentZone, spB))
                    self.target_graph.add((spB, BOT.adjacentZone, spA))
                    horiz += 1
                    if cross_unit:
                        party += 1
                elif has_slab:
                    # Vertical connectivity — use bot:intersectsZone (TBox v0.16.0)
                    self.target_graph.add((spA, BOT.intersectsZone, spB))
                    self.target_graph.add((spB, BOT.intersectsZone, spA))
                    vert += 1

        # bot:intersectsZone is declared in TBox v0.16.0; no manual OWL.ObjectProperty
        # triple needed here. The inline schema declarations in _OBJECT_PROPS handle
        # the Protégé display case when TBox is not yet imported.

        self.stats['adjacency_horizontal'] = horiz
        self.stats['adjacency_party_wall']  = party
        self.stats['adjacency_vertical']    = vert

        print(f"  水平相邻 horizontal pairs: {horiz}  "
              f"(其中跨单元 cross-unit party wall: {party})")
        print(f"  垂直连通 vertical pairs:    {vert}")
        print(f"  bot:adjacentZone 三元组已写入 (双向): {horiz * 2}")

    # ── P2: fireRating → ficr:hasREI ──────────────────────────────────────────

    @staticmethod
    def _parse_fire_rating(raw: str) -> Optional[int]:
        """解析 fireRating 字符串为整数分钟 (P2)。

        支持格式:
          "1 HR" / "2 HR"       → 60, 120
          "EI30 S200" / "EI60"  → 30, 60  (提取 I 后数字)
          "REI60"               → 60
          "30 min"              → 30
          "None", "Fire Rating" → None (跳过)
        """
        if not raw:
            return None
        raw = raw.strip()

        # 跳过占位符
        if raw.lower() in ('none', 'fire rating', ''):
            return None

        # 模式: "N HR" 或 "N hr"
        m = re.match(r'(\d+)\s*[Hh][Rr]', raw)
        if m:
            return int(m.group(1)) * 60

        # 模式: EI30, REI60, EI30 S200 (提取 I 后紧跟的数字)
        m = re.search(r'[RE]*I(\d+)', raw)
        if m:
            return int(m.group(1))

        # 模式: "N min"
        m = re.match(r'(\d+)\s*min', raw, re.IGNORECASE)
        if m:
            return int(m.group(1))

        return None

    def _map_fire_ratings(self) -> None:
        """从源图解析 fireRating 并写入 ficr:hasREI (xsd:integer) (P2)。"""
        print("\n正在映射 fireRating → ficr:hasREI ...")
        print("Mapping fire ratings to ficr:hasREI ...")

        fire_prop = PROPS['fireRating_property_simple']
        count = 0

        for subject in set(self.source_graph.subjects(fire_prop)):
            raw_val = str(self.source_graph.value(subject, fire_prop) or '')
            minutes = self._parse_fire_rating(raw_val)
            if minutes is not None:
                self.target_graph.add((
                    subject, FICR.hasREI,
                    Literal(minutes, datatype=XSD.integer)
                ))
                count += 1

        self.stats['fire_ratings_mapped'] = count
        print(f"  ficr:hasREI written: {count}")

    # ── P3: ExternalWall inference ────────────────────────────────────────────

    def _classify_walls(self) -> None:
        """将 ficr:Wall + isExternal=true 重分类为 ficr:ExternalWall (P3)。"""
        print("\n正在推断外墙子类型 ...")
        print("Classifying external walls ...")

        count = 0
        for wall in list(self.target_graph.subjects(RDF.type, FICR.Wall)):
            ext_val = self.target_graph.value(wall, FICR.isExternal)
            if ext_val is not None and str(ext_val).lower() == 'true':
                self.target_graph.remove((wall, RDF.type, FICR.Wall))
                self.target_graph.add((wall, RDF.type, FICR.ExternalWall))
                count += 1

        self.stats['walls_external'] = count
        print(f"  ficr:ExternalWall: {count}")

    # ── P5: isStoreyAbove / isStoreyBelow ─────────────────────────────────────

    def _link_storeys(self) -> None:
        """按标高排序楼层，写入 ficr:isStoreyAbove / ficr:isStoreyBelow (P5)。"""
        print("\n正在连接楼层排序关系 ...")
        print("Linking storeys by elevation ...")

        link_count = 0

        # 查找 MultiStoreyBuilding（由 _classify_building 设置）
        for building in self.target_graph.subjects(RDF.type, FICR.MultiStoreyBuilding):
            storeys = list(self.target_graph.objects(building, BOT.hasStorey))
            if len(storeys) < 2:
                continue

            # 收集 (storey, elevation) 对
            storey_elev = []
            for s in storeys:
                elev = self.target_graph.value(s, FICR.hasElevation)
                if elev is not None:
                    try:
                        storey_elev.append((s, float(str(elev))))
                    except (ValueError, TypeError):
                        pass

            # 按标高升序排序
            storey_elev.sort(key=lambda x: x[1])

            # 写入连续楼层关系
            for i in range(len(storey_elev) - 1):
                lower, _ = storey_elev[i]
                upper, _ = storey_elev[i + 1]
                self.target_graph.add((upper, FICR.isStoreyAbove, lower))
                self.target_graph.add((lower, FICR.isStoreyBelow, upper))
                link_count += 1

        self.stats['storey_links'] = link_count
        print(f"  Storey link pairs: {link_count}")

    def convert(self) -> None:
        """执行转换"""
        print("\n开始转换...")
        print("Starting conversion...")
        
        self._setup_namespaces()
        
        # 遍历所有主语
        for subject in set(self.source_graph.subjects()):
            # 跳过 props: 命名空间的主语（属性定义）
            if str(subject).startswith(str(PROPS)):
                continue
            
            # 转换类型
            for obj_type in self.source_graph.objects(subject, RDF.type):
                # 跳过属性定义
                if obj_type in [OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty]:
                    continue
                
                mapped_type = self._map_class(obj_type)
                self.target_graph.add((subject, RDF.type, mapped_type))
                
                # 统计类数量
                type_str = mapped_type.n3(self.target_graph.namespace_manager)
                if ':' in type_str:
                    _, local_name = type_str.split(':', 1)
                    self.stats['class_counts'][local_name] = \
                        self.stats['class_counts'].get(local_name, 0) + 1
            
            # 转换属性
            for prop, value in self.source_graph.predicate_objects(subject):
                if prop == RDF.type:
                    continue
                
                result = self._convert_property(subject, prop, value)
                if result:
                    new_prop, new_value = result
                    self.target_graph.add((subject, new_prop, new_value))

        # 推断建筑/楼层/空间子类型 (Changes B, C, D + P0-P5)
        self._classify_building()        # Change B + P4: hasNumberOfStoreys
        self._classify_storeys()         # Change C
        self._link_storeys()             # P5: isStoreyAbove/Below
        self._classify_members()         # P0: beo:Member 消歧
        self._classify_spaces()          # Change D + P1: 扩展 OmniClass 规则
        self._classify_walls()           # P3: ExternalWall 推断
        self._map_fire_ratings()         # P2: fireRating → hasREI

        # 推断空间连通性（source 图读取，target 图写入）
        self._infer_space_adjacency()

        self.stats['total_triples'] = len(self.target_graph)
        print(f"\n转换完成，生成了 {self.stats['total_triples']} 条三元组")
        print(f"Conversion completed, generated {self.stats['total_triples']} triples")
    
    def save(self, output_file: str) -> None:
        """保存转换后的图"""
        print(f"\n正在保存到: {output_file}")
        print(f"Saving to: {output_file}")
        
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        
        # 序列化为 Turtle 格式
        ttl_content = self.target_graph.serialize(format='turtle')
        
        # 后处理：统一数值类型为 xsd:decimal，修复科学计数法
        ttl_content = self._post_process_numbers(ttl_content)
        
        # 添加文件头注释（无 owl:imports，避免 Protégé SAXParseException）
        ttl_content = self._add_file_header(ttl_content, output_file)
        
        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(ttl_content)
        
        print("保存完成 Save completed")
    
    def _post_process_numbers(self, ttl_content: str) -> str:
        """后处理：将 xsd:double 统一为 xsd:decimal，展开科学计数法。

        ━━━ 为什么删除步骤 2 / 3 ━━━
        rdflib 的 Turtle 序列化器输出的已经是完全合法的 Turtle：
          true / false → 裸布尔关键字（W3C Turtle §2.5 合法缩写）
          60 / 23.450  → 裸整数 / 裸小数（同上）

        Turtle 规范要求：带 ^^ 类型标注的字面量必须有引号，即 "value"^^<type>。
        在裸关键字后直接追加 ^^type（例如 true^^xsd:boolean）产生非法语法。
        非法语法导致 OWL API 的 Turtle 解析器报错，进而回退到 XML 解析器，
        XML 解析器在第 1 列遇到 # 字符后抛出：
            SAXParseException: Content is not allowed in prolog

        结论：步骤 2/3 是该报错的根本原因，已删除。
        """
        # 步骤 0：xsd:double → xsd:decimal（rdflib 边缘情况兜底）
        ttl_content = ttl_content.replace('^^xsd:double', '^^xsd:decimal')
        ttl_content = ttl_content.replace(
            '^^<http://www.w3.org/2001/XMLSchema#double>',
            '^^<http://www.w3.org/2001/XMLSchema#decimal>'
        )

        # 步骤 1：科学计数法 → 定点小数（rdflib 对极大/极小浮点数偶尔使用 eE 格式）
        def _fmt(m):
            try:
                return f"{float(m.group(0)):.3f}"
            except Exception:
                return m.group(0)

        ttl_content = re.sub(
            r'(?<=\s)[-+]?\d*\.?\d+[eE][-+]?\d+(?=\s|;|\^|$)',
            _fmt, ttl_content, flags=re.MULTILINE
        )
        return ttl_content
    
    # ── Inline schema declarations injected into every ABox output ─────────────
    # These mirror a subset of ficr_tbox.ttl so Protégé / OWL API treats
    # predicates as typed OWL properties even before the TBox is imported.
    # All values verified against ficr_tbox.ttl v0.16.0.

    _DATATYPE_PROPS: Dict[str, str] = {
        # ficr: local name → xsd: range local name
        # All values verified against ficr_tbox.ttl v0.16.0.
        "hasArea":                   "decimal",
        "hasBuildingHeight":         "decimal",   # v0.16.0: max-min storey elevation
        "hasCombinedGrossFloorArea": "decimal",   # v0.16.0: sum of space areas
        "hasElevation":              "decimal",
        "hasID":                     "string",
        "hasLength":                 "decimal",
        "hasNumberOfStoreys":        "integer",   # P4: storey count on buildings
        "hasREI":                    "integer",   # P2: fire resistance in minutes
        "hasStoreyHeight":           "decimal",   # Change 3: new in v0.15.0
        "hasThickness":              "decimal",
        "hasTopStoreyFloorHeight":   "decimal",   # v0.16.0: elevation of topmost above-ground storey
        "hasTopStoreyHeight":        "decimal",   # v0.16.0: storey height of topmost storey
        "hasVolume":                 "decimal",
        "hasWidth":                  "decimal",
        "isAboveGround":             "boolean",   # v0.16.0: storey above/below ground
        "isExternal":                "boolean",
        "isLoadBearing":             "boolean",
    }

    _OBJECT_PROPS: list = [
        # ficr: object properties used in the converted ABox
        # All verified against TBox v0.16.0
        "hasSpaceUsage",     # space usage classification (Change D)
        "isStoreyAbove",     # P5: storey ordering
        "isStoreyBelow",     # P5: storey ordering
    ]

    _BOT_OBJECT_PROPS: list = [
        "adjacentElement", "adjacentZone", "containsElement",
        "hasBuilding", "hasSpace", "hasStorey", "hasSubElement",
        "intersectsZone",
    ]

    _FICR_CLASSES: list = [
        "Wall", "ExternalWall", "Floor", "FloorSlab", "RoofSlab", "Doorset", "Window",
        "Ceiling", "Stair", "StairFlight", "Railing",
        "Beam", "Column", "WallFoundation", "Furnishings", "Opening",
        "MultiStoreyBuilding", "SingleStoreyBuilding",
        "GroundAndAboveStorey", "BasementStorey",
        "RoomSpace", "StairSpace", "RoofSpace", "ShaftSpace", "LiftShaft",
        "ServiceShaft", "AtriumSpace", "BalconySpace", "CavitySpace", "DuctSpace",
    ]

    _BOT_CLASSES: list = [
        "Building", "Storey", "Space", "Element",
    ]

    def _build_schema_declarations(self) -> str:
        """
        Build a Turtle snippet that declares the OWL types of all properties
        and classes used in this ABox.

        Why inline declarations?
        ─────────────────────────
        OWL API / Protégé treats any predicate without a type declaration as
        an annotation property. The full ficr_tbox.ttl is not embedded here,
        but we need at least rdf:type owl:DatatypeProperty / owl:ObjectProperty
        on every predicate so the Properties panel shows them correctly.

        When the user later imports ficr_tbox.ttl (Active Ontology → Ontology
        Imports → Add Direct Import), these stubs are superseded by the full
        TBox definitions. They do not conflict.
        """
        BOT_NS  = "https://w3id.org/bot#"
        FICR_NS = "https://w3id.org/bam/ficr#"
        XSD_NS  = "http://www.w3.org/2001/XMLSchema#"
        OWL_NS  = "http://www.w3.org/2002/07/owl#"

        lines = [
            "# ── Inline schema declarations (ficr_tbox.ttl v0.16.0 subset) ──",
            "# These let Protégé / OWL API recognise property types without",
            "# requiring ficr_tbox.ttl to be loaded. They are safe to override",
            "# once the TBox is imported.",
        ]

        # DatatypeProperties
        for local, xsd_local in sorted(self._DATATYPE_PROPS.items()):
            lines.append(
                f"<{FICR_NS}{local}> a <{OWL_NS}DatatypeProperty> ;\n"
                f"    rdfs:range <{XSD_NS}{xsd_local}> ."
            )

        # ficr: ObjectProperties
        for local in self._OBJECT_PROPS:
            lines.append(f"<{FICR_NS}{local}> a <{OWL_NS}ObjectProperty> .")

        # bot: ObjectProperties
        for local in self._BOT_OBJECT_PROPS:
            lines.append(f"<{BOT_NS}{local}> a <{OWL_NS}ObjectProperty> .")

        # ficr: Classes
        for local in self._FICR_CLASSES:
            lines.append(f"<{FICR_NS}{local}> a <{OWL_NS}Class> .")

        # bot: Classes
        for local in self._BOT_CLASSES:
            lines.append(f"<{BOT_NS}{local}> a <{OWL_NS}Class> .")

        return "\n".join(lines) + "\n"

    def _add_file_header(self, ttl_content: str, output_file: str) -> str:
        """
        Assemble the final output:

          1. Comment block       — human-readable header
          2. @prefix block       — from rdflib (preserved as-is)
          3. owl:Ontology block  — with owl:imports pointing to the FiCR TBox
          4. Inline declarations — minimal OWL property/class stubs
          5. Instance data       — the converted ABox triples

        ━━━ Two problems fixed here ━━━

        Problem A — SAXParseException (fixed in _post_process_numbers):
          Caused by broken Turtle syntax. Once the Turtle is valid the Turtle
          parser is used and SAX is never invoked.

        Problem B — "only annotations" in Protégé (fixed here):
          OWL API treats any predicate with no rdf:type declaration as an
          annotation property. The inline declarations in step 4 fix this.

        ━━━ owl:imports strategy ━━━
        The owl:Ontology block includes:
          owl:imports <https://w3id.org/bam/ficr>

        If Protégé has internet access, it fetches the TBox automatically.
        If not (local development), the inline declarations in step 4 are
        sufficient for property typing. The user can also add the TBox manually:
          Active Ontology → Ontology Imports → Add Direct Import → ficr_tbox.ttl
        """
        base_name   = os.path.splitext(os.path.basename(output_file))[0]
        abox_iri    = f"https://lbd.example.com/instances/{base_name}"
        tbox_iri    = "https://w3id.org/bam/ficr"

        # ── 1. Comment block ────────────────────────────────────────────────
        comment = (
            f"# FiCR ABox Instance Data — {base_name}\n"
            f"# TBox: {tbox_iri}  (ficr_tbox.ttl v0.16.0)\n"
            f"#\n"
            f"# Opening in Protégé\n"
            f"#   Option A (online):  owl:imports resolves automatically.\n"
            f"#   Option B (offline): Active Ontology → Ontology Imports\n"
            f"#                       → Add Direct Import → ficr_tbox.ttl\n"
            f"\n"
        )

        # ── 2. @prefix block ─────────────────────────────────────────────────
        lines = ttl_content.split('\n')

        # Ensure owl: prefix is present
        if not any('@prefix owl:' in ln for ln in lines):
            for i, ln in enumerate(lines):
                if ln.strip().startswith('@prefix'):
                    lines.insert(i + 1,
                                 '@prefix owl: <http://www.w3.org/2002/07/owl#> .')
                    break

        # Split into prefix lines and instance-data lines
        prefix_lines, data_lines = [], []
        past_prefixes = False
        for ln in lines:
            if ln.strip().startswith('@prefix'):
                prefix_lines.append(ln)
                past_prefixes = True
            elif past_prefixes:
                data_lines.append(ln)

        prefix_block = '\n'.join(prefix_lines) + '\n'

        # ── 3. owl:Ontology block ────────────────────────────────────────────
        ontology_block = (
            f"\n"
            f"<{abox_iri}>\n"
            f"    a owl:Ontology ;\n"
            f'    rdfs:comment "FiCR ABox — converted from LBD/IFC. '
            f'Import ficr_tbox.ttl for full reasoning."@en ;\n'
            f"    owl:imports <{tbox_iri}> .\n"
            f"\n"
        )

        # ── 4. Inline schema declarations ────────────────────────────────────
        schema_block = "\n" + self._build_schema_declarations() + "\n"

        # ── 5. Instance data ─────────────────────────────────────────────────
        # Skip the existing owl:Ontology triple that _was_ in the content
        # (inserted by a previous call or present from rdflib)
        filtered_data = '\n'.join(
            ln for ln in data_lines
            if 'owl:Ontology' not in ln
        )

        return (
            comment
            + prefix_block
            + ontology_block
            + schema_block
            + filtered_data
        )
    
    def print_statistics(self) -> None:
        """打印转换统计信息"""
        print("\n" + "=" * 60)
        print("转换统计信息 Conversion Statistics")
        print("=" * 60)
        
        for class_name in sorted(self.stats['class_counts'].keys()):
            count = self.stats['class_counts'][class_name]
            print(f"  {class_name}: {count}")
        
        print(f"\n属性统计 Property Statistics:")
        print(f"  - 已转换属性 Converted properties: {self.stats['converted_properties']}")
        print(f"  - 保留关系 Preserved relations: {self.stats['preserved_relations']}")
        print(f"  - 未映射属性 Unmapped properties: {self.stats['unmapped_properties']}")

        print(f"\n子类型推断 Subclass Inference:")
        print(f"  - 建筑分类 Buildings classified:   {self.stats['buildings_classified']}")
        print(f"  - 楼层分类 Storeys classified:     {self.stats['storeys_classified']}")
        print(f"  - 空间(OmniClass) Spaces(OmniClass): {self.stats['spaces_classified_omniclass']}")
        print(f"  - 空间(文本) Spaces(text):         {self.stats['spaces_classified_text']}")
        print(f"  - 空间(未分类) Spaces(unclassified): {self.stats['spaces_unclassified']}")

        print(f"\n构件分类 Member Classification (P0):")
        print(f"  - 楼梯构件 StairFlight:      {self.stats.get('members_stair', 0)}")
        print(f"  - 幕墙竖框 Mullion(Element): {self.stats.get('members_mullion', 0)}")
        print(f"  - 梁 Beam:                   {self.stats.get('members_beam', 0)}")

        print(f"\n耐火等级 Fire Ratings (P2):")
        print(f"  - ficr:hasREI mapped:        {self.stats.get('fire_ratings_mapped', 0)}")

        print(f"\n外墙分类 External Walls (P3):")
        print(f"  - ficr:ExternalWall:         {self.stats.get('walls_external', 0)}")

        print(f"\n楼层连接 Storey Links (P5):")
        print(f"  - isStoreyAbove/Below pairs: {self.stats.get('storey_links', 0)}")

        print(f"\n空间连通性 Space Adjacency:")
        print(f"  - 水平相邻对 Horizontal pairs:    {self.stats.get('adjacency_horizontal', 0)}")
        print(f"  - 跨单元隔墙 Party-wall pairs:    {self.stats.get('adjacency_party_wall', 0)}")
        print(f"  - 垂直连通对 Vertical pairs:      {self.stats.get('adjacency_vertical', 0)}")

        print(f"\n总三元组 Total triples: {self.stats['total_triples']}")


def convert_single_file(input_file: str, output_file: str, ontology_path: str = "FiCR_ontology/ficr_tbox.ttl") -> None:
    """转换单个文件"""
    converter = LBDToFiCRConverter(ontology_path)
    converter._load_ontology()
    converter.load_source(input_file)
    converter.convert()
    converter.save(output_file)
    converter.print_statistics()


def convert_batch(input_dir: str, output_dir: str, ontology_path: str = "FiCR_ontology/ficr_tbox.ttl") -> None:
    """批量转换目录中的所有 TTL 文件"""
    print(f"使用 ontology: {ontology_path}")
    print(f"Using ontology: {ontology_path}")
    
    ttl_files = [f for f in os.listdir(input_dir) if f.endswith('.ttl')]
    
    if not ttl_files:
        print(f"在 {input_dir} 中未找到 TTL 文件")
        print(f"No TTL files found in {input_dir}")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    for ttl_file in ttl_files:
        print("\n" + "=" * 60)
        print(f"正在处理文件: {ttl_file}")
        print(f"Processing file: {ttl_file}")
        print("=" * 60)
        
        input_path = os.path.join(input_dir, ttl_file)
        output_filename = ttl_file.replace('.ttl', '_ficr.ttl')
        output_path = os.path.join(output_dir, output_filename)
        
        try:
            convert_single_file(input_path, output_path, ontology_path)
        except Exception as e:
            print(f"错误 Error: {str(e)}")
            continue


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法 Usage:")
        print("  单文件转换: python lbd_to_ficr_converter.py input.ttl [output.ttl]")
        print("  批量转换: python lbd_to_ficr_converter.py --batch input_dir [output_dir]")
        sys.exit(1)
    
    ontology_path = "FiCR_ontology/ficr_tbox.ttl"
    if not os.path.exists(ontology_path):
        print(f"错误: Ontology 文件不存在: {ontology_path}")
        sys.exit(1)
    
    if sys.argv[1] == '--batch':
        input_dir = sys.argv[2] if len(sys.argv) > 2 else "ifcs2lbd/ifc2lbd_outputs"
        output_dir = sys.argv[3] if len(sys.argv) > 3 else "FiCR_with_instances"
        convert_batch(input_dir, output_dir, ontology_path)
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.ttl', '_ficr.ttl')
        convert_single_file(input_file, output_file, ontology_path)


if __name__ == "__main__":
    main()