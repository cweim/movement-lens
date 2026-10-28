"""Primary studies for bounded, general football recovery education."""
VERSION = 'football-cluster-context-v1'
CATEGORIES = [
    {'id':'descriptive','label':'Descriptive posture pattern','meaning':'A numerical posture group; no specific football action is confirmed.'},
    {'id':'running','label':'Running-like locomotion','meaning':'The reviewer considers the examples running-like. This does not measure speed, sprinting, intensity or all group members.'},
    {'id':'stepping','label':'Upright stepping','meaning':'The reviewer considers the examples upright stepping. This does not establish speed or workload.'},
    {'id':'turning','label':'Lowering / turning posture','meaning':'The reviewer considers the examples lowering or reorientation. Hard braking or acceleration has not been measured.'},
    {'id':'mixed','label':'Mixed / uncertain','meaning':'Examples cannot confidently be assigned one action. Do not attribute a specific physiological demand to the cluster.'},
]
STUDIES = [
    {'id':'paper:nedelec2014','title':'Playing actions and recovery kinetics after soccer',
     'url':'https://pubmed.ncbi.nlm.nih.gov/24172722/','kind':'activity_association',
     'design':'Observational; ten professional players, four matches, fourteen observations.',
     'finding':'Some measured short-sprint and hard direction-change frequencies were associated with subsequent soreness or jump-performance changes.',
     'limits':'Small observational sample. Measured football actions and recovery tests differ from pose clusters; this is not a cluster-to-treatment rule.'},
    {'id':'paper:varley2017','title':'Match activity and subsequent fatigue measures',
     'url':'https://pubmed.ncbi.nlm.nih.gov/29339989/','kind':'activity_association',
     'design':'Ten professional players around two matches; activity and follow-up recovery measures.',
     'finding':'Measured accelerations, decelerations and some sprint variables were associated with subsequent biochemical or perceived-wellness measures.',
     'limits':'Associations do not validate projected posture groups, estimate individual muscle loading, or establish the recovery needed by this player.'},
    {'id':'paper:ascensao2011','title':'Water immersion after a one-off soccer match',
     'url':'https://pubmed.ncbi.nlm.nih.gov/21170794/','kind':'recovery_intervention',
     'design':'Randomized trial in twenty male soccer players, comparing cold and thermoneutral water immersion after one match.',
     'finding':'Some muscle-damage, discomfort and neuromuscular-function outcomes favoured cold immersion over the comparison condition.',
     'limits':'Small, specific protocol and population; no untreated control. Does not show that a particular pose cluster needs immersion or prescribe a protocol for Marcelo.'},
    {'id':'paper:kinugasa2009','title':'Comparing post-match recovery strategies in youth soccer',
     'url':'https://pubmed.ncbi.nlm.nih.gov/19620926/','kind':'recovery_intervention',
     'design':'Twenty-eight young players across three matches with randomized recovery modalities.',
     'finding':'Combined immersion and active recovery improved some perceived-recovery outcomes, but did not substantially improve jump height versus the alternatives.',
     'limits':'Youth population, short follow-up and outcome-dependent results. Perceived improvement is not a universal performance or treatment benefit.'},
]
