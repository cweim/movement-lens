"""Small curated evidence library; original summaries, no runtime web requests."""
PAPERS = [
    {'id': 'paper:nedelec2014', 'title': 'Soccer playing actions and recovery kinetics',
     'url': 'https://pubmed.ncbi.nlm.nih.gov/24172722/', 'year': 2014,
     'summary': 'An observational study in ten professional players found associations between some match actions and subsequent soreness or performance changes. Recovery was assessed before and after matches.',
     'applicability': 'It measured recovery outcomes. It does not validate these pose descriptors or prescribe recovery from a similarity count.'},
    {'id': 'paper:varley2017', 'title': 'Match activity, fatigue and neuromuscular performance',
     'url': 'https://pubmed.ncbi.nlm.nih.gov/29339989/', 'year': 2017,
     'summary': 'In ten professional players around two matches, some acceleration, deceleration and sprint measures were associated with subsequent fatigue-related measures.',
     'applicability': 'Associations used measured match activity and follow-up assessments, not pose-cluster frequencies.'},
    {'id': 'paper:tan2025', 'title': 'Weekly acceleration/deceleration loads and neuromuscular performance',
     'url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC12590203/', 'year': 2025,
     'summary': 'A two-week study of thirty-nine U19 outfield players observed neuromuscular declines but no significant correlations between individual-session acceleration/deceleration loads and the measured impairments.',
     'applicability': 'Recovery relationships depend on context and timescale; there is no universal movement-count-to-recovery rule.'},
    {'id': 'paper:opencap2023', 'title': 'OpenCap: Human movement dynamics from smartphone videos',
     'url': 'https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011462', 'year': 2023,
     'summary': 'OpenCap combined calibrated multi-view smartphone video, 3D reconstruction and musculoskeletal simulation, with validation against motion capture, force plates and muscle-activity measurements.',
     'applicability': 'This broadcast application measures projected 2D descriptors. OpenCap accuracy and muscle-loading estimates cannot be transferred to it.'},
    {'id': 'paper:viewpoint2025', 'title': 'Camera viewing angle and OpenPose validity',
     'url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC11819822/', 'year': 2025,
     'summary': 'A controlled experiment demonstrated that camera viewpoint affects the validity of joint-angle estimates from OpenPose.',
     'applicability': 'It was not a football or YOLO validation. Inspect perspective, occlusion and source clips when comparing projected angles.'},
]

REGIONS = {
    'left_knee': 'Left projected knee', 'right_knee': 'Right projected knee',
    'left_hip': 'Left projected hip', 'right_hip': 'Right projected hip',
    'trunk': 'Projected trunk inclination', 'leg_spacing': 'Torso-scaled leg spacing',
}


def region_for(feature):
    return 'leg_spacing' if feature.startswith('ankle_separation') else next(
        (r for r in REGIONS if feature.startswith(r)), 'trunk')


def region_context(region):
    return {'region': region, 'label': REGIONS[region],
            'description': ('Separation of the two ankle keypoints relative to torso length. This is not an anatomical ankle angle.'
                            if region == 'leg_spacing' else
                            'A projected image-plane descriptor. The body map locates measurements; it does not measure muscle activity or tissue load.'),
            'research_ids': ['paper:viewpoint2025', 'paper:opencap2023'],
            'recovery_question': 'What symptoms, recent exposure and staff assessments accompany this observed pattern?'}
